"""問答 Service（業務邏輯層）。

將完整的 RAG 問答流程從 router 抽離，符合 SRP：
    - Router：只處理 HTTP 協議（SSE 格式、狀態碼）
    - ChatService：協調安全檢查、查詢強化、搜索、LLM 生成

所有依賴透過建構子注入（DIP）。
"""
from __future__ import annotations

import json
import time
from typing import AsyncIterator, Callable, Any


class _ThinkFilter:
    """Strips <think>...</think> reasoning traces from streamed tokens.

    Buffers tokens while inside a <think> block and logs them at DEBUG level
    instead of forwarding to the client.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_think = False

    def feed(self, token: str) -> str:
        """Return the portion of *token* that should be sent to the client."""
        self._buf += token
        out = ""

        while self._buf:
            if self._in_think:
                end = self._buf.find("</think>")
                if end == -1:
                    # still inside — consume everything, keep possible partial tag
                    if len(self._buf) > 8:
                        logger.debug(f"[think] {self._buf[:-8]}")
                        self._buf = self._buf[-8:]
                    break
                else:
                    logger.debug(f"[think] {self._buf[:end]}")
                    self._buf = self._buf[end + 8:]
                    self._in_think = False
            else:
                start = self._buf.find("<think>")
                if start == -1:
                    # no think block — flush everything except possible partial tag
                    if len(self._buf) > 7:
                        out += self._buf[:-7]
                        self._buf = self._buf[-7:]
                    break
                else:
                    out += self._buf[:start]
                    self._buf = self._buf[start + 7:]
                    self._in_think = True

        return out

    def flush(self) -> str:
        """Flush remaining buffer after stream ends (only if not in a think block)."""
        if self._in_think:
            logger.debug(f"[think] {self._buf}")
            self._buf = ""
            return ""
        out = self._buf
        self._buf = ""
        return out

from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from src.core.domain.search_result import SearchResult
from src.core.interfaces.query_enhancer import IQueryEnhancer
from src.core.interfaces.repository import IChatSessionRepository
from src.core.interfaces.search import ISearchEngine
from src.core.interfaces.security import IInputValidator, IOutputSanitizer

# System Prompt 定義助理角色與行為約束
_DEFAULT_SYSTEM_PROMPT = """你是一位專業的職涯分析師，根據職涯顧問的影片內容協助使用者解決職涯問題。
請依據以下從影片逐字稿擷取的參考段落回答問題，內容包含履歷撰寫、面試技巧、職涯規劃與薪資談判等主題。
若參考段落中未包含相關資訊，請誠實說明，切勿自行捏造建議。
回答應以繁體中文撰寫，語調專業而親切。引用影片內容時請附上影片標題。
回答前先拆解問題的核心需求，從參考段落中找出最相關的建議，再提供具體、有條理的回應。

【參考段落】
{context}
"""

# 提示詞快取 TTL（秒）— 避免每次請求都查詢 DB
_PROMPT_CACHE_TTL = 300


class ChatService:
    """問答業務邏輯服務。

    職責（SRP，每項委派給注入的依賴）：
        1. 輸入驗證   → IInputValidator
        2. 查詢強化   → IQueryEnhancer
        3. 混合搜索   → ISearchEngine
        4. LLM 串流生成 → LLM（透過 ILLMProvider 建立）
        5. 輸出過濾   → IOutputSanitizer
        6. 對話記憶   → ConversationBufferWindowMemory（per session）
        7. Session 持久化 → IChatSessionRepository（可選）
        8. 訊息數量限制 → max_messages_per_session
    """

    def __init__(
        self,
        input_validator: IInputValidator,
        output_sanitizer: IOutputSanitizer,
        query_enhancer: IQueryEnhancer,
        search_engine: ISearchEngine,
        llm,  # BaseLanguageModel（由 ILLMProvider.build_llm() 建立）
        embed_query_fn: Callable[[str], list[float]],
        memory_window: int = 10,
        session_repo: IChatSessionRepository | None = None,
        max_messages_per_session: int = 100,
        db_session_factory: Any | None = None,
    ) -> None:
        self._input_validator = input_validator
        self._output_sanitizer = output_sanitizer
        self._query_enhancer = query_enhancer
        self._search_engine = search_engine
        self._llm = llm
        self._embed_query = embed_query_fn
        self._memory_window = memory_window
        self._session_repo = session_repo
        self._max_messages = max_messages_per_session
        self._db_session_factory = db_session_factory
        # per-session 對話記憶（key: session_id）
        self._memories: dict[str, ConversationBufferWindowMemory] = {}
        # 提示詞快取 (content, cached_at)
        self._prompt_cache: tuple[str, float] | None = None
        # 語意快取服務（可選，None 表示停用）
        self._semantic_cache: Any | None = None

    async def stream_answer(
        self,
        question: str,
        session_id: str = "default",
        user_id: int | None = None,
        topic: str | None = None,
    ) -> AsyncIterator[str]:
        """執行完整 RAG 問答流程，以 async generator 串流回傳 token。

        Args:
            question:   已通過 DTO 驗證的使用者問題
            session_id: 對話 session 識別碼
            user_id:    發送問題的使用者 ID（用於 Session 持久化）

        Yields:
            LLM 逐 token 輸出（已過輸出過濾）

        Raises:
            HTTPException 429: 已達訊息上限
        """
        from fastapi import HTTPException, status
        from src.infrastructure.repositories.chat_session_repository import SQLAlchemyChatSessionRepository

        # 若有 db_session_factory，每次建立新的 session_repo（避免 singleton 持有 DB session）
        session_repo = self._session_repo
        _db = None
        if session_repo is None and self._db_session_factory is not None and user_id is not None:
            _db = self._db_session_factory()
            session_repo = SQLAlchemyChatSessionRepository(_db)

        # 0. 若有 session_repo，檢查訊息上限並確保 session 存在
        if session_repo is not None and user_id is not None:
            # 確保 Session 存在（第一次問答時自動建立）
            existing = await session_repo.find_by_session_id(session_id)
            if not existing:
                title = question[:50] if question else None
                await session_repo.create_session(session_id, user_id, title)

            # 檢查訊息上限
            count = await session_repo.get_message_count(session_id)
            if count >= self._max_messages:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="已達訊息上限，請開新對話",
                )
            
            # 立即持久化使用者訊息（讓切換 Session 或重整時能即時看到問題）
            await session_repo.add_message(session_id, "user", question)
            await session_repo.increment_message_count(session_id)

        # 1. 安全檢查與輸入清洗（由 IInputValidator 負責）
        clean_input = self._input_validator.check_input(question)

        # 2. 查詢強化：術語正規化（由 IQueryEnhancer 負責）
        enhanced_query = self._query_enhancer.enhance_query(clean_input)

        # 2.5 語意快取查詢（有命中則直接串流回傳，跳過搜索與 LLM）
        if self._semantic_cache is not None:
            cached = await self._semantic_cache.lookup(enhanced_query)
            if cached is not None:
                cached_answer, _ = cached
                logger.debug(f"[ChatService] Semantic cache HIT for session={session_id}")
                memory = self._get_memory(session_id)
                # 逐 chunk 串流回傳快取結果（維持 SSE 相容性）
                chunk_size = 20
                full_response = cached_answer
                for i in range(0, len(cached_answer), chunk_size):
                    yield cached_answer[i : i + chunk_size]
                memory.save_context({"input": question}, {"output": full_response})
                if session_repo is not None and user_id is not None:
                    assistant_msg = await session_repo.add_message(session_id, "assistant", full_response)
                    await session_repo.increment_message_count(session_id)
                    yield f'[META:{{"message_id":{assistant_msg.id}}}]'
                return

        # 3. 向量化 + 混合搜索（由 ISearchEngine 負責）
        query_embedding = self._embed_query(enhanced_query)
        results = self._search_engine.search(enhanced_query, query_embedding, topic=topic)

        # 4. 組裝 Context
        context = self._build_context(results)

        # 5. 組裝訊息列表（含對話歷史）
        memory = self._get_memory(session_id)
        history_messages = memory.load_memory_variables({}).get("history", [])
        system_prompt = await self._get_system_prompt()
        messages = [SystemMessage(content=system_prompt.format(context=context))]
        if isinstance(history_messages, list):
            messages.extend(history_messages)
        messages.append(HumanMessage(content=question))

        # 6. LLM 串流生成 + 輸出過濾（含 <think> 推理段落過濾）
        full_response = ""
        think_filter = _ThinkFilter()
        async for chunk in self._llm.astream(messages):
            token = chunk.content
            full_response += token
            visible = think_filter.feed(token)
            if visible:
                safe_token = self._output_sanitizer.sanitize_output(visible)
                yield safe_token
        # flush any remaining buffer after stream ends
        remaining = think_filter.flush()
        if remaining:
            safe_token = self._output_sanitizer.sanitize_output(remaining)
            yield safe_token

        # 7. 儲存對話記憶
        memory.save_context({"input": question}, {"output": full_response})

        # 7.4 傳送來源資訊（YouTube 影片引用）
        sources_data = [
            {"title": r.video_title, "url": r.url, "topic": r.section, "score": round(r.score, 3)}
            for r in results
            if r.url
        ]
        if sources_data:
            yield f'[SOURCES:{json.dumps(sources_data, ensure_ascii=False)}]'

        # 7.5 將結果存入語意快取（不阻塞串流）
        if self._semantic_cache is not None:
            sources = [
                {"source": r.source, "section": r.section, "score": round(r.score, 4)}
                for r in results
            ]
            try:
                await self._semantic_cache.store(enhanced_query, full_response, sources)
            except Exception as exc:
                logger.warning(f"[ChatService] Failed to store semantic cache: {exc}")

        # 8. 持久化助理回覆至資料庫（user 訊息已在 step 0 儲存）
        if session_repo is not None and user_id is not None:
            assistant_msg = await session_repo.add_message(session_id, "assistant", full_response)
            await session_repo.increment_message_count(session_id)
            yield f'[META:{{"message_id":{assistant_msg.id}}}]'
            if self._db_session_factory is not None and self._session_repo is None:
                await _db.close()

        logger.info(
            f"[ChatService] session={session_id} "
            f"q_len={len(question)} a_len={len(full_response)}"
        )

    def set_semantic_cache(self, cache: Any) -> None:
        """注入語意快取服務（啟動後可動態設定）。"""
        self._semantic_cache = cache

    def get_sources(self, question: str, topic: str | None = None) -> list[dict]:
        """取得問題的相關典籍來源（不執行 LLM）。"""
        enhanced_query = self._query_enhancer.enhance_query(question)
        query_embedding = self._embed_query(enhanced_query)
        results = self._search_engine.search(enhanced_query, query_embedding, topic=topic)
        return [
            {
                "source": r.source,
                "section": r.section,
                "score": round(r.score, 4),
                "page_number": r.page_number,
                "video_title": r.video_title,
                "upload_date": r.upload_date,
                "url": r.url,
            }
            for r in results
        ]

    async def _get_system_prompt(self) -> str:
        """取得系統提示詞（優先從 DB 讀取啟用的提示詞，並以 5 分鐘快取減少 DB 查詢）。"""
        now = time.monotonic()
        if self._prompt_cache is not None:
            content, cached_at = self._prompt_cache
            if now - cached_at < _PROMPT_CACHE_TTL:
                return content

        if self._db_session_factory is None:
            return _DEFAULT_SYSTEM_PROMPT

        try:
            from src.infrastructure.repositories.system_prompt_repository import (
                SQLAlchemySystemPromptRepository,
            )
            async with self._db_session_factory() as db:
                repo = SQLAlchemySystemPromptRepository(db)
                actives = await repo.get_all_active()
            if actives:
                content = "\n\n".join(p.content for p in actives)
                if "{context}" not in content:
                    logger.warning(
                        "[ChatService] 啟用中的 system prompt 缺少 {context} 佔位符，"
                        "將 fallback 至預設提示詞，避免 RAG 文件內容被靜默丟棄"
                    )
                else:
                    self._prompt_cache = (content, now)
                    return content
        except Exception as exc:
            logger.warning(f"[ChatService] 無法從 DB 讀取系統提示詞，使用預設值：{exc}")

        return _DEFAULT_SYSTEM_PROMPT

    def _get_memory(self, session_id: str) -> ConversationBufferWindowMemory:
        """取得或建立指定 session 的對話記憶。"""
        if session_id not in self._memories:
            self._memories[session_id] = ConversationBufferWindowMemory(
                k=self._memory_window,
                return_messages=True,
            )
        return self._memories[session_id]

    @staticmethod
    def _build_context(results: list[SearchResult]) -> str:
        """將搜索結果格式化為 System Prompt 的參考段落文字。"""
        if not results:
            return "（未找到相關段落）"
        parts = []
        for i, r in enumerate(results, start=1):
            title_label = f"《{r.video_title}》" if r.video_title else ""
            section_label = f"【{r.section}】" if r.section else ""
            parts.append(f"[{i}] {title_label}{section_label}{r.content}")
        return "\n\n".join(parts)
