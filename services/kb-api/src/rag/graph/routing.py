"""Deterministic router：決定 relevance check 之後走哪個 Node。

刻意不讓 LLM 決定路由（見 docs/graph-design/graph-security-design.md
「Router 的 Enum 邊界」）——LLM 只產出 `sufficient: bool`，
路由本身是純 Python if/else。
"""
from __future__ import annotations

from typing import Literal

from .nodes import MAX_ITERATIONS
from .state import RetrievalGraphState

RouteDecision = Literal["rewrite", "build_context"]


def route_after_relevance_check(state: RetrievalGraphState) -> RouteDecision:
    """對應 target-graph-design.md 的 R2 決策點。

    relevance_sufficient == True
        → build_context
    relevance_sufficient == False AND retry_count < MAX_ITERATIONS - 1
        → rewrite
    relevance_sufficient == False AND retry_count >= MAX_ITERATIONS - 1
        → build_context（fallback，帶 relevance_sufficient=False）
    """
    if state.relevance_sufficient:
        return "build_context"
    if state.retry_count < MAX_ITERATIONS - 1:
        return "rewrite"
    return "build_context"
