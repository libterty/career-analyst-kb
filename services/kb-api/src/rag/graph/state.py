"""Agentic RAG Retrieval Graph 的 State Schema。

欄位取捨依據見 docs/graph-design/graph-state-schema.md。
State 只活在單一 request 生命週期內，不落地持久化。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from src.core.domain.search_result import SearchResult
from src.graph.errors import GraphError
from src.graph.node import NodeResult

Status = Literal["running", "succeeded", "failed"]


@dataclass(frozen=True)
class RetrievalGraphState:
    """Agentic RAG retrieval graph 的共享狀態（immutable，透過 dataclasses.replace 更新）。"""

    # ── Immutable inputs ──────────────────────────────────────────────
    execution_id: str
    question: str
    sub_questions: tuple[str, ...] = ()
    started_at: float = field(default_factory=time.monotonic)

    # ── Mutable — 允許覆寫（每輪迭代更新）────────────────────────────
    normalized_input: str = ""
    chunk_pool: tuple[SearchResult, ...] = ()
    missing_aspects: tuple[str, ...] = ()
    relevance_sufficient: bool = False
    current_node: str = ""
    status: Status = "running"

    # ── Mutable — 只能單向遞增 ────────────────────────────────────────
    retry_count: int = 0

    # ── Append-only ───────────────────────────────────────────────────
    node_results: tuple[NodeResult, ...] = ()
    errors: tuple[GraphError, ...] = ()

    # ── Output ────────────────────────────────────────────────────────
    final_context: str = ""
    updated_at: float = field(default_factory=time.monotonic)

    @staticmethod
    def new(question: str, sub_questions: list[str] | None = None) -> "RetrievalGraphState":
        return RetrievalGraphState(
            execution_id=str(uuid.uuid4()),
            question=question,
            sub_questions=tuple(sub_questions or ()),
        )
