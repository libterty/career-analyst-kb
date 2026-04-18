"""安全層介面（Interface Segregation Principle）。

將輸入驗證與輸出過濾拆成獨立介面，
符合 ISP：呼叫端只需依賴它真正使用的介面。
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class IInputValidator(ABC):
    """輸入驗證介面。

    SecurityGuardrail 實作此介面，ChatService 透過此介面驗證輸入。
    """

    @abstractmethod
    def check_input(self, user_input: str) -> str:
        """驗證並清洗使用者輸入。

        Args:
            user_input: 使用者原始輸入

        Returns:
            通過安全檢查的清洗文字

        Raises:
            SecurityError: 當輸入被封鎖時
        """


class IOutputSanitizer(ABC):
    """輸出過濾介面。"""

    @abstractmethod
    def sanitize_output(self, llm_output: str) -> str:
        """過濾 LLM 輸出，防止機密資訊外洩。"""
