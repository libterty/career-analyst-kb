"""Phase 4 — Prompt Injection Detector
多層次偵測：規則式 + 語意相似度 + LLM 判斷。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger


class ThreatLevel(str, Enum):
    """威脅等級分類。

    SAFE:       安全，可正常處理
    SUSPICIOUS: 可疑，記錄日誌但允許通過
    BLOCKED:    封鎖，直接拒絕請求
    """
    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    BLOCKED = "blocked"


@dataclass
class DetectionResult:
    """注入偵測結果。

    Attributes:
        threat_level:    威脅等級
        reason:          封鎖或標記的原因說明
        matched_pattern: 觸發的規則名稱（用於日誌追蹤）
    """
    threat_level: ThreatLevel
    reason: Optional[str] = None
    matched_pattern: Optional[str] = None


# ---- 硬封鎖規則（Pattern-based detection rules）--------------------- #
# 每個 tuple：(正則表達式, 規則說明)
# 這些規則一旦匹配，請求直接被 BLOCKED

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # 經典「忽略指令」攻擊（英文）
    (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", "Ignore-instruction attack"),
    (r"disregard\s+(your\s+)?(system\s+)?prompt", "Disregard-prompt attack"),
    (r"forget\s+(everything|all)\s+(you|i|we)\s+(were|have|told)", "Forget-instruction attack"),

    # 角色扮演越獄（讓 AI 扮演「沒有限制的版本」）
    (r"pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(different|unrestricted|evil|bad)", "Roleplay jailbreak"),
    (r"你(現在|從現在起)是?.*(沒有限制|不受約束|邪惡|駭客)", "中文角色扮演注入"),
    (r"假設你是?.*(不受道德|沒有規則|反派)", "中文角色扮演注入"),

    # System Prompt 擷取攻擊（試圖讓 AI 洩漏系統指令）
    (r"(print|repeat|show|reveal|output)\s+(your\s+)?(system\s+prompt|instructions|rules)", "System prompt extraction"),
    (r"(告訴我|顯示|輸出).*(系統提示|指令|規則)", "中文系統提示擷取"),

    # 分隔符注入（試圖插入 LLM 模板標籤欺騙模型）
    (r"</?(system|user|assistant|human|context)>", "XML/delimiter injection"),
    (r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", "LLM template injection"),

    # 上下文操縱
    (r"the\s+above\s+was\s+(a\s+)?test", "Context manipulation"),
    (r"now\s+do\s+the\s+opposite\s+of", "Opposite instruction attack"),

    # 資料外洩嘗試（試圖讓 AI 將對話傳送到外部）
    (r"send\s+(all|this|the)\s+(data|conversation|history)\s+to", "Data exfiltration attempt"),
]

# 預先編譯所有正則，避免每次請求重複編譯（效能優化）
_COMPILED_PATTERNS = [(re.compile(pat, re.IGNORECASE | re.DOTALL), label) for pat, label in _INJECTION_PATTERNS]


# ---- 可疑訊號（軟封鎖，記錄日誌但不直接拒絕）----------------------- #
# 這些關鍵字單獨出現不一定是攻擊，但值得記錄

_SUSPICIOUS_SIGNALS = [
    r"ignore",
    r"pretend",
    r"假裝",
    r"override",
    r"jailbreak",
    r"DAN",           # "Do Anything Now"，常見越獄前綴
    r"developer\s+mode",
]

_COMPILED_SUSPICIOUS = [re.compile(s, re.IGNORECASE) for s in _SUSPICIOUS_SIGNALS]

# 輸入長度上限（字元數）；過長的輸入可能是資料填塞攻擊
MAX_INPUT_LENGTH = 2000


class InjectionDetector:
    """多層次 Prompt Injection 偵測器。

    層次一：輸入長度檢查（快速過濾）
    層次二：硬封鎖規則匹配（BLOCKED）
    層次三：可疑訊號偵測（SUSPICIOUS，記錄審核）
    """

    def detect(self, text: str) -> DetectionResult:
        """偵測輸入文字是否含有注入攻擊。

        Args:
            text: 使用者輸入的原始文字

        Returns:
            DetectionResult 包含威脅等級與原因
        """
        # 層次一：長度檢查（超長輸入直接封鎖）
        if len(text) > MAX_INPUT_LENGTH:
            return DetectionResult(
                threat_level=ThreatLevel.BLOCKED,
                reason=f"Input exceeds maximum length ({MAX_INPUT_LENGTH} chars)",
            )

        # 層次二：硬封鎖規則匹配
        for pattern, label in _COMPILED_PATTERNS:
            if pattern.search(text):
                logger.warning(f"[Security] Injection blocked: {label} | input_preview={text[:80]!r}")
                return DetectionResult(
                    threat_level=ThreatLevel.BLOCKED,
                    reason=f"Detected pattern: {label}",
                    matched_pattern=label,
                )

        # 層次三：可疑訊號偵測（軟封鎖，記錄後放行）
        for pattern in _COMPILED_SUSPICIOUS:
            if pattern.search(text):
                logger.info(f"[Security] Suspicious input flagged: {text[:80]!r}")
                return DetectionResult(
                    threat_level=ThreatLevel.SUSPICIOUS,
                    reason="Input contains suspicious keywords",
                )

        return DetectionResult(threat_level=ThreatLevel.SAFE)
