"""Agentic RAG — Query Rewriter

根據 RelevanceChecker 回傳的缺漏面向，改寫查詢以補撈缺失段落。

設計原則：
- 使用 fastLLM（qwen3:4b）
- cosine similarity 保護：改寫後與原始 query embedding 相似度 > 0.85 時不改寫，
  避免無效迴圈（LLM 沒真的改變意思）
- LLM 或 embed 呼叫失敗時 fallback 回傳原 query，不阻斷主流程
"""
from __future__ import annotations

import math

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import HumanMessage
from loguru import logger

_COSINE_THRESHOLD = 0.85

_PROMPT_TEMPLATE = """你是一位搜尋查詢改寫專家。

原始問題：{question}

知識庫中缺少以下面向的資訊：
{missing_aspects}

請將原始問題改寫成更能找到上述缺漏面向的搜尋查詢。
要求：
1. 保留原始問題的核心意圖
2. 在查詢中融入缺漏的面向
3. 繁體中文，50 字以內
4. 只輸出改寫後的查詢，不要任何解釋或標點符號以外的內容

改寫後的查詢："""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class QueryRewriter:
    def __init__(self, llm: BaseLanguageModel, embedder) -> None:
        """
        Args:
            llm:     fastLLM 實例
            embedder: EmbeddingService 實例（需有 embed_query(text) -> list[float]）
        """
        self._llm = llm
        self._embedder = embedder

    def rewrite(self, original: str, missing_aspects: list[str]) -> str:
        """改寫查詢以補撈缺漏面向。

        Args:
            original:        使用者原始問題
            missing_aspects: RelevanceChecker 回傳的缺漏面向列表

        Returns:
            改寫後的查詢字串；若改寫無效或失敗，回傳 original
        """
        if not missing_aspects:
            return original

        aspects_text = "\n".join(f"- {a}" for a in missing_aspects)
        prompt = _PROMPT_TEMPLATE.format(
            question=original,
            missing_aspects=aspects_text,
        )

        try:
            response = self._llm.invoke([HumanMessage(content=prompt)])
            rewritten = response.content if hasattr(response, "content") else str(response)
            rewritten = rewritten.strip().strip("「」\"""")
        except Exception as exc:
            logger.warning(f"[QueryRewriter] LLM call failed, returning original: {exc}")
            return original

        if not rewritten or rewritten == original:
            return original

        # cosine similarity 保護：改寫後若與原始 query 太相似，代表 LLM 沒真的改變意思
        try:
            orig_emb = self._embedder.embed_query(original)
            new_emb = self._embedder.embed_query(rewritten)
            similarity = _cosine_similarity(orig_emb, new_emb)
            if similarity > _COSINE_THRESHOLD:
                logger.debug(
                    f"[QueryRewriter] cosine={similarity:.3f} > {_COSINE_THRESHOLD}, "
                    "rewrite too similar to original, skipping"
                )
                return original
        except Exception as exc:
            logger.warning(f"[QueryRewriter] embed failed during similarity check: {exc}")
            # embed 失敗時仍使用改寫結果（有改寫總比沒有好）

        logger.info(f"[QueryRewriter] {original!r} → {rewritten!r}")
        return rewritten
