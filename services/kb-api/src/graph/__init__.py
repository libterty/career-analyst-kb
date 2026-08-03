"""輕量 Graph/State-Machine 執行核心。

刻意保持極簡（不是通用 workflow engine）：
    - 沒有持久化 Checkpoint（本次唯一使用者 AgenticRAG retrieval graph
      執行時間 < 5 秒，不需要跨 process 恢復，見
      docs/graph-design/graph-reliability-design.md）。
    - 沒有 DSL／YAML 定義，Graph 直接以 Python 函式組裝，方便型別檢查與測試。

選用理由與框架比較見 docs/graph-design/graph-migration-plan.md。
"""
from __future__ import annotations

from .errors import ErrorCategory, GraphError
from .node import Node, NodeResult
from .runner import GraphRunner

__all__ = [
    "ErrorCategory",
    "GraphError",
    "Node",
    "NodeResult",
    "GraphRunner",
]
