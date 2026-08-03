"""GraphRunner — 依序或平行執行 Node，並把結果寫回一個新的 state 物件。

刻意不做的事（見 docs/graph-design/graph-migration-plan.md）：
    - 不做跨 process 持久化 Checkpoint。
    - 不提供 DSL；Graph 的節點順序與路由邏輯由呼叫端（如
      src/rag/graph/build.py）以一般 Python coroutine 組裝。
"""
from __future__ import annotations

import dataclasses
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger

from .errors import ErrorCategory
from .node import NodeResult, run_node

StateT = TypeVar("StateT")


class GraphRunner:
    """執行單個 Node 並將結果套用到 state，附帶 observability 記錄。

    設計上刻意輕量：呼叫端自行決定 Node 執行順序/分支/平行呼叫
    （用一般的 `await`／`asyncio.gather`），GraphRunner 只負責
    「執行一個 Node → 記錄 NodeResult → 回傳更新後的 state」這件重複的事。
    """

    def __init__(self, execution_id: str) -> None:
        self._execution_id = execution_id

    async def step(
        self,
        state: StateT,
        node_name: str,
        fn: Callable[[StateT], Awaitable[dict[str, Any]]],
        *,
        error_category: ErrorCategory = ErrorCategory.INTERNAL,
        max_attempts: int = 1,
    ) -> tuple[StateT, NodeResult]:
        """執行一個 Node，套用重試政策，回傳 (新 state, NodeResult)。

        `max_attempts > 1` 只用於明確標示為 Infrastructure retry 的 Node
        （如 RetrieveNode 對 Milvus 的呼叫），且不做 backoff——
        本地服務重試延遲沒有意義（見 graph-reliability-design.md）。
        """
        result = await run_node(node_name, fn, state, on_error_category=error_category)
        for attempt in range(2, max_attempts + 1):
            if result.error is None:
                break
            logger.warning(
                f"[Graph:{self._execution_id}] {node_name} attempt {attempt - 1} failed "
                f"({result.error.message}), retrying"
            )
            result = await run_node(node_name, fn, state, on_error_category=error_category)

        new_state = self._apply(state, result)

        logger.debug(
            f"[Graph:{self._execution_id}] node={node_name} "
            f"duration_ms={result.duration_ms:.1f} error={result.error} "
            f"route={result.route_decision}"
        )
        return new_state, result

    @staticmethod
    def _apply(state: StateT, result: NodeResult) -> StateT:
        """用 dataclasses.replace 產生新 state（不 mutate 原物件）。

        node_results/errors 是 append-only 欄位：這裡負責把它們接上去，
        而不是讓每個 Node 自己維護 list（避免平行 Node 互相覆蓋）。
        """
        updates = dict(result.updates)
        node_results = list(getattr(state, "node_results", [])) + [result]
        updates["node_results"] = node_results
        if result.error is not None:
            errors = list(getattr(state, "errors", [])) + [result.error]
            updates["errors"] = errors
        return dataclasses.replace(state, **updates)
