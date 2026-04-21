"""Chat Router（精簡 HTTP 層）。

Router 只負責：
    - 接收 HTTP 請求、驗證 DTO
    - 呼叫 ChatService（業務邏輯）
    - 格式化 SSE 串流或 JSON 回應

安全檢查、查詢強化、搜索、LLM 生成均已移至 ChatService。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from src.api.auth import get_current_user
from src.api.dependencies import get_chat_service
from src.application.dto.chat_dto import ChatRequestDTO, ChatResponseDTO, SourceDocumentDTO
from src.application.services.chat_service import ChatService
from src.core.exceptions import SecurityError

router = APIRouter(prefix="/api/chat", tags=["Chat"])

ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]

# SSE keepalive interval (seconds) — prevents clients from dropping the
# connection while RAG search + LLM cold-start takes time before the first token.
_KEEPALIVE_INTERVAL = 15


@router.post("/query")
async def chat_query(
    request: ChatRequestDTO,
    current_user=Depends(get_current_user),
    chat_service: ChatServiceDep = None,
):
    """串流問答端點（Server-Sent Events）。

    回應格式為 text/event-stream，每個 token 以 `data: token\\n\\n` 格式推送，
    最後以 `data: [DONE]\\n\\n` 表示結束。

    在等待 LLM 產生第一個 token 期間，每 15 秒發送一個 SSE comment
    (`: keepalive`) 維持連線，避免用戶端 timeout。
    """
    session_id = request.session_id or str(uuid.uuid4())

    async def event_stream():
        queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

        async def _run() -> None:
            try:
                async for token in chat_service.stream_answer(
                    request.question, session_id, user_id=current_user.id, topic=request.topic
                ):
                    await queue.put(("data", token))
                await queue.put(("done", None))
            except SecurityError as e:
                await queue.put(("error", str(e)))
            except Exception as exc:
                logger.exception(f"[Chat] Stream error: {exc}")
                await queue.put(("error", "系統發生錯誤，請稍後再試"))

        task = asyncio.create_task(_run())
        try:
            while True:
                try:
                    kind, value = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_INTERVAL
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if kind == "done":
                    yield "data: [DONE]\n\n"
                    break
                elif kind == "error":
                    yield f"data: [ERROR] {value}\n\n"
                    break
                else:
                    yield f"data: {value}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/query/sync", response_model=ChatResponseDTO)
async def chat_query_sync(
    request: ChatRequestDTO,
    current_user=Depends(get_current_user),
    chat_service: ChatServiceDep = None,
):
    """非串流問答端點（等待完整回答後一次回傳）。"""
    session_id = request.session_id or str(uuid.uuid4())

    try:
        tokens: list[str] = []
        async for token in chat_service.stream_answer(
            request.question, session_id, user_id=current_user.id, topic=request.topic
        ):
            tokens.append(token)
    except SecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))

    answer = "".join(tokens)
    sources = chat_service.get_sources(request.question, topic=request.topic)

    return ChatResponseDTO(
        answer=answer,
        session_id=session_id,
        sources=[SourceDocumentDTO(**s) for s in sources],
    )
