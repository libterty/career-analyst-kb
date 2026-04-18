"""Phase 4 — Security Guardrail
統一安全檢查入口，整合 InjectionDetector + ContentFilter。

實作 IInputValidator 與 IOutputSanitizer 介面，
ChatService 透過介面依賴，不直接引入此具體類別。
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.exceptions import SecurityError  # 集中管理例外
from src.core.interfaces.security import IInputValidator, IOutputSanitizer
from .content_filter import ContentFilter
from .injection_detector import InjectionDetector, ThreatLevel


@dataclass
class GuardrailResult:
    """安全檢查的完整結果（目前主要透過 check_input / sanitize_output 使用）。

    Attributes:
        safe:           是否通過所有安全檢查
        cleaned_input:  清洗後的輸入文字
        cleaned_output: 清洗後的輸出文字
        audit_events:   本次請求觸發的審計事件列表（用於日誌）
    """
    safe: bool
    cleaned_input: str
    cleaned_output: str
    audit_events: list[str]


class SecurityGuardrail(IInputValidator, IOutputSanitizer):
    """統一安全檢查入口，所有 API 請求都必須通過此關卡。

    輸入檢查流程（check_input）：
        1. InjectionDetector：偵測 Prompt Injection 攻擊
        2. ContentFilter：過濾有害內容（製毒、自傷等）

    輸出過濾流程（sanitize_output）：
        - ContentFilter：過濾一貫道機密口訣、PII 個資等
    """

    def __init__(self) -> None:
        self._injection = InjectionDetector()
        self._filter = ContentFilter()

    def check_input(self, user_input: str) -> str:
        """驗證並清洗使用者輸入。若被封鎖則拋出 SecurityError。

        Args:
            user_input: 使用者原始輸入

        Returns:
            通過安全檢查後的清洗文字

        Raises:
            SecurityError: 當輸入被 Injection Detector 或 Content Filter 封鎖時
        """
        events: list[str] = []

        # 第一關：Prompt Injection 偵測
        detection = self._injection.detect(user_input)
        if detection.threat_level == ThreatLevel.BLOCKED:
            logger.warning(f"[Guardrail] Input BLOCKED: {detection.reason}")
            raise SecurityError(f"您的提問包含不允許的內容：{detection.reason}")

        if detection.threat_level == ThreatLevel.SUSPICIOUS:
            # 可疑但不封鎖，記錄審計事件供後台審核
            events.append(f"suspicious_input: {detection.reason}")
            logger.info(f"[Guardrail] Suspicious input logged for review")

        # 第二關：有害內容過濾（製毒、自傷等）
        filter_result = self._filter.filter_input(user_input)
        if not filter_result.is_clean:
            logger.warning(f"[Guardrail] Input filtered: {filter_result.violations}")
            raise SecurityError("您的提問包含不允許的敏感內容，請修改後再試。")

        return filter_result.filtered_text

    def sanitize_output(self, llm_output: str) -> str:
        """過濾 LLM 輸出，防止機密資訊外洩（逐 token 呼叫）。

        Args:
            llm_output: LLM 生成的文字片段

        Returns:
            過濾後的文字（若有敏感詞則替換為佔位符）
        """
        result = self._filter.filter_output(llm_output)
        if not result.is_clean:
            logger.warning(f"[Guardrail] Output filtered: {result.violations}")
        return result.filtered_text
