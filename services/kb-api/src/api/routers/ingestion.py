"""Ingestion Router — YouTube SSE 觸發端點。

POST /api/ingestion/youtube
    以 Server-Sent Events 串流回傳 ingest_youtube.py 的執行進度。
    需要 admin 權限。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from loguru import logger

from src.api.auth import get_current_user

router = APIRouter(prefix="/api/ingestion", tags=["Ingestion"])

ROOT = Path(__file__).parent.parent.parent.parent


def _require_admin(current_user=Depends(get_current_user)):
    from fastapi import HTTPException, status
    if getattr(current_user, "role", None) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理員權限必要")
    return current_user


@router.post("/youtube")
async def ingest_youtube(
    incremental: bool = Query(default=True, description="True 表示跳過已匯入的影片"),
    _admin=Depends(_require_admin),
):
    """觸發 YouTube 逐字稿匯入，以 SSE 串流回傳進度。

    事件格式：
        data: <log line>\\n\\n
        data: [DONE]\\n\\n   — 完成
        data: [ERROR] ...\\n\\n — 失敗
    """
    cmd = [sys.executable, str(ROOT / "scripts" / "ingest_youtube.py")]
    if incremental:
        cmd.append("--incremental")

    async def event_stream():
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(ROOT),
            )
            assert proc.stdout is not None
            async for line in proc.stdout:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    yield f"data: {text}\n\n"
            await proc.wait()
            if proc.returncode == 0:
                yield "data: [DONE]\n\n"
            else:
                yield f"data: [ERROR] process exited with code {proc.returncode}\n\n"
        except Exception as exc:
            logger.exception(f"[Ingestion] SSE error: {exc}")
            yield f"data: [ERROR] {exc}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
