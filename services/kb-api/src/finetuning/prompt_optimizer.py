"""Query enhancement utilities used by the chat and RAG pipelines."""
from __future__ import annotations

import re

from src.core.interfaces.query_enhancer import IQueryEnhancer


class PromptOptimizer(IQueryEnhancer):
    """Lightweight query enhancer.

    The previous codebase expected a finetuning-backed optimizer module, but the
    implementation file is no longer present. This fallback keeps the runtime
    contract intact without changing existing call sites.
    """

    _TERM_MAP: dict[str, str] = {
        "1on1": "一對一",
        "one on one": "一對一",
        "on call": "值班",
        "sre": "site reliability engineer",
        "pm": "product manager",
    }

    def enhance_query(self, query: str) -> str:
        normalized = self._normalize_whitespace(query)
        lowered = normalized.lower()

        for alias, canonical in self._TERM_MAP.items():
            lowered = re.sub(rf"\b{re.escape(alias)}\b", canonical, lowered)

        return lowered.strip()

    def build_glossary_context(self, query: str) -> str:
        matched_terms = [
            f"{alias}={canonical}"
            for alias, canonical in self._TERM_MAP.items()
            if alias in query.lower()
        ]
        return "；".join(matched_terms)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
