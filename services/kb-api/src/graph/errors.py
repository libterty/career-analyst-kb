"""Graph 錯誤分類。

刻意跟一般 Exception 分開，因為同一個 try/except 不該把
「Milvus 逾時」「LLM 判斷內容不足」「Model API 呼叫失敗」混為一談
（見 docs/graph-design/graph-reliability-design.md 的 Retry 分類表）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCategory(str, Enum):
    """Node 失敗的分類，驅動不同的 Retry / Fallback 策略。"""

    INFRA = "infra"
    """外部系統（Milvus/DB）連線層錯誤，可重試。"""

    MODEL_FALLBACK = "model_fallback"
    """LLM 呼叫失敗或輸出無法解析，Node 已內部降級（非重試）。"""

    INTERNAL = "internal"
    """純運算邏輯拋出非預期例外，代表程式錯誤而非暫態錯誤，不重試。"""

    TIMEOUT = "timeout"
    """Node 或整體 Graph 執行超過 deadline。"""


@dataclass(frozen=True)
class GraphError:
    """記錄一次 Node 失敗事件（append-only，寫入 state.errors）。"""

    node_name: str
    category: ErrorCategory
    message: str
