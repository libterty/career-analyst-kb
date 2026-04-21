"""Phase 4 — Content Filter
雙向過濾：輸入敏感詞 + LLM 輸出敏感詞，防止資訊洩漏與不當內容。
使用 Microsoft Presidio 進行 PII 偵測。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from loguru import logger

# Presidio 為可選依賴，未安裝時停用 PII 偵測功能
try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    _PRESIDIO_AVAILABLE = True
except ImportError:
    _PRESIDIO_AVAILABLE = False
    logger.warning("presidio not installed; PII detection disabled")


@dataclass
class FilterResult:
    """內容過濾結果。

    Attributes:
        is_clean:      是否通過過濾（無違規）
        filtered_text: 過濾後的文字（違規部分替換為佔位符）
        violations:    觸發的違規規則列表
    """
    is_clean: bool
    filtered_text: str
    violations: list[str]


# 系統機密詞（禁止出現在 LLM 輸出中）
# 這些資訊依教義規定須由點傳師當面傳授，不可以文字形式公開
_INTERNAL_SENSITIVE_PATTERNS = [
    (r"三寶\s*口訣", "三寶口訣（機密傳授，不得文字記錄）"),
    (r"合同\s*手勢", "合同手勢（機密傳授，不得公開）"),
    (r"玄關\s*竅\s*位置", "玄關竅位置（需點傳師當面指引）"),
    (r"密語|密訣|密傳", "密傳內容"),
]

# 一般有害內容（輸入與輸出都過濾）
_HARMFUL_PATTERNS = [
    (r"(製作|合成|取得)\s*(爆炸物|毒品|武器)", "有害製作指引"),
    (r"(自殺|自傷)\s*(方法|教學|步驟)", "自傷內容"),
    (r"(兒童|未成年).*(色情|性)", "不當性內容"),
]

# 輸出過濾包含兩類：機密詞 + 有害內容
_ALL_PATTERNS = [
    (re.compile(p, re.IGNORECASE), label)
    for p, label in (_INTERNAL_SENSITIVE_PATTERNS + _HARMFUL_PATTERNS)
]


class ContentFilter:
    """雙向內容過濾器。

    輸入過濾（filter_input）：
        - 只過濾有害內容
        - 用戶可以「詢問」三寶口訣，但回答中不會出現

    輸出過濾（filter_output）：
        - 過濾機密詞 + 有害內容
        - 額外使用 Presidio 偵測 PII（姓名、電話、身分證號等個資）
    """

    def __init__(self) -> None:
        if _PRESIDIO_AVAILABLE:
            # 初始化 Presidio 分析引擎與匿名化引擎
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
        else:
            self._analyzer = None
            self._anonymizer = None

    def filter_input(self, text: str) -> FilterResult:
        """過濾使用者輸入中的有害內容。

        注意：輸入不過濾機密詞，因為使用者可能合理地詢問這些概念。
        實際保護在輸出層執行。
        """
        # 輸入只過濾有害內容
        harmful_patterns = [
            (re.compile(p, re.IGNORECASE), label)
            for p, label in _HARMFUL_PATTERNS
        ]
        violations: list[str] = []
        filtered = text
        for pattern, label in harmful_patterns:
            if pattern.search(text):
                violations.append(label)
                filtered = pattern.sub(f"[{label}（已過濾）]", filtered)
        return FilterResult(is_clean=not violations, filtered_text=filtered, violations=violations)

    def filter_output(self, text: str) -> FilterResult:
        """過濾 LLM 輸出中的機密詞與有害內容，並偵測個資（PII）。

        執行順序：
            1. 規則過濾（機密詞 + 有害內容）
            2. Presidio PII 偵測（若安裝且步驟 1 通過）
        """
        result = self._apply_patterns(text, direction="output")
        # 只有在規則過濾通過後才做 PII 偵測（避免多餘處理）
        if _PRESIDIO_AVAILABLE and result.is_clean:
            result = self._filter_pii(result.filtered_text)
        return result

    # ------------------------------------------------------------------

    def _apply_patterns(self, text: str, direction: str) -> FilterResult:
        """對文字套用所有正則規則，回傳過濾結果。"""
        violations: list[str] = []
        for pattern, label in _ALL_PATTERNS:
            if pattern.search(text):
                violations.append(label)
                logger.warning(f"[ContentFilter] {direction} violation: {label}")

        if violations:
            # 將所有違規內容替換為佔位符（例如「[三寶口訣（已過濾）]」）
            filtered = text
            for pattern, label in _ALL_PATTERNS:
                filtered = pattern.sub(f"[{label}（已過濾）]", filtered)
            return FilterResult(is_clean=False, filtered_text=filtered, violations=violations)

        return FilterResult(is_clean=True, filtered_text=text, violations=[])

    def _filter_pii(self, text: str) -> FilterResult:
        """使用 Presidio 偵測並匿名化個人識別資訊（PII）。

        目前只支援英文 PII 偵測（Presidio 中文支援有限）。
        偵測到的 PII 會被自動替換為泛型佔位符（如 <PERSON>）。
        """
        results = self._analyzer.analyze(text=text, language="en")
        if not results:
            return FilterResult(is_clean=True, filtered_text=text, violations=[])

        anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results)
        violations = [r.entity_type for r in results]
        logger.info(f"[ContentFilter] PII detected and anonymized: {violations}")
        return FilterResult(is_clean=False, filtered_text=anonymized.text, violations=violations)
