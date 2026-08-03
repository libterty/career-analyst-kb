"""Node 契約。

每個 Node 是一個 async callable：`(state) -> NodeResult`。
Node 不得直接修改傳入的 state（符合專案 immutability 慣例）——
它只回傳新的欄位值，由 GraphRunner 統一寫回一個新的 state 物件。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .errors import ErrorCategory, GraphError


@dataclass(frozen=True)
class NodeResult:
    """單次 Node 執行的結果與 observability metadata。

    `updates` 是要寫回 state 的欄位（by name），GraphRunner 會用
    `dataclasses.replace()` 產生新的 state 物件，Node 本身不 mutate state。
    """

    node_name: str
    duration_ms: float
    updates: dict[str, Any] = field(default_factory=dict)
    route_decision: str | None = None
    error: GraphError | None = None
    retryable: bool = False


class Node(Protocol):
    """Node 的最小介面：一個有名字、可執行的 async callable。"""

    name: str

    async def __call__(self, state: Any) -> NodeResult: ...


async def run_node(
    name: str,
    fn: Callable[[Any], Awaitable[dict[str, Any]]],
    state: Any,
    *,
    on_error_category: ErrorCategory = ErrorCategory.INTERNAL,
) -> NodeResult:
    """執行單個 Node 函式並包裝成 NodeResult（含耗時、錯誤分類）。

    `fn` 只需回傳要寫回 state 的欄位 dict；若拋出例外，
    捕捉並記錄為 GraphError，但不重拋（Node 不應讓整個 Graph 崩潰，
    除非是 non-recoverable 的程式錯誤——那種情況仍由呼叫端的
    on_error_category 決定是否視為 retryable）。
    """
    start = time.monotonic()
    try:
        updates = await fn(state)
        duration_ms = (time.monotonic() - start) * 1000
        return NodeResult(node_name=name, duration_ms=duration_ms, updates=updates)
    except Exception as exc:  # noqa: BLE001 — Node 邊界必須攔截所有例外並分類
        duration_ms = (time.monotonic() - start) * 1000
        return NodeResult(
            node_name=name,
            duration_ms=duration_ms,
            updates={},
            error=GraphError(node_name=name, category=on_error_category, message=str(exc)[:500]),
        )
