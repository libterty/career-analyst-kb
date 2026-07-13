"""Custom FastAPI middleware."""
from __future__ import annotations

import contextvars
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ContextVar so any log statement in the request lifecycle can read the ID.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Stamp every request with a short UUID, attach it to response headers.

    The ID is stored in ``request_id_var`` so service-layer code can include
    it in log messages without threading the value through every call.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request_id_var.set(request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
