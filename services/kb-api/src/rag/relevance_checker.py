"""Agentic RAG — Relevance Checker

給定使用者問題和一批 chunk，判斷這些 chunk 是否足以回答問題。
若不足，回傳缺漏的面向供 QueryRewriter 改寫查詢。

設計原則：
- 使用 fastLLM（qwen3:4b）降低 latency
- 每個 chunk 只取前 80 字，避免 prompt 過長
- LLM 呼叫或解析失敗時 fallback sufficient=True，不阻斷主流程
- chunk 數 < 2 時直接判定 insufficient，不浪費 LLM call
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import HumanMessage
from loguru import logger

from src.core.domain.search_result import SearchResult

_CHUNK_PREVIEW_CHARS = 80

_PROMPT_TEMPLATE = """你是一位 RAG 系統品質評估員。
使用者問題：{question}

以下是從知識庫檢索到的段落（共 {n} 段）：
{chunks_summary}

請判斷這些段落是否足以回答上述問題。

回答格式（嚴格遵守）：
第一行：SUFFICIENT 或 INSUFFICIENT
第二行起（INSUFFICIENT 時才需要）：列出缺少的面向，每行一項，以「-」開頭，最多 3 項。

範例 1（足夠）：
SUFFICIENT

範例 2（不足）：
INSUFFICIENT
- 缺乏具體的行動步驟
- 沒有提到新人場景
"""


@dataclass(frozen=True)
class RelevanceResult:
    sufficient: bool
    missing_aspects: list[str] = field(default_factory=list)
    confidence: float = 1.0


class RelevanceChecker:
    def __init__(self, llm: BaseLanguageModel) -> None:
        self._llm = llm

    def check(self, question: str, chunks: list[SearchResult]) -> RelevanceResult:
        """判斷 chunks 是否足以回答 question。

        Args:
            question: 使用者原始問題
            chunks:   hybrid search 回傳的結果列表

        Returns:
            RelevanceResult，sufficient=True 表示可直接進 LLM 生成
        """
        if len(chunks) < 2:
            logger.debug(f"[RelevanceChecker] chunk count={len(chunks)} < 2 → insufficient")
            return RelevanceResult(
                sufficient=False,
                missing_aspects=["相關段落數量不足"],
                confidence=0.9,
            )

        chunks_summary = self._build_summary(chunks)
        prompt = _PROMPT_TEMPLATE.format(
            question=question,
            n=len(chunks),
            chunks_summary=chunks_summary,
        )

        try:
            response = self._llm.invoke([HumanMessage(content=prompt)])
            raw = response.content if hasattr(response, "content") else str(response)
            return self._parse(raw)
        except Exception as exc:
            logger.warning(f"[RelevanceChecker] LLM call failed, fallback sufficient=True: {exc}")
            return RelevanceResult(sufficient=True, confidence=0.5)

    @staticmethod
    def _build_summary(chunks: list[SearchResult]) -> str:
        parts = []
        for i, c in enumerate(chunks, start=1):
            preview = c.content[:_CHUNK_PREVIEW_CHARS].replace("\n", " ")
            label = f"【{c.section}】" if c.section else ""
            parts.append(f"[{i}] {label}{preview}…")
        return "\n".join(parts)

    @staticmethod
    def _parse(raw: str) -> RelevanceResult:
        # strip <think> tags (local reasoning models emit these)
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        lines = [l.strip() for l in cleaned.splitlines() if l.strip()]

        if not lines:
            logger.warning("[RelevanceChecker] empty LLM response, fallback sufficient=True")
            return RelevanceResult(sufficient=True, confidence=0.5)

        verdict = lines[0].upper()

        if "SUFFICIENT" in verdict and "INSUFFICIENT" not in verdict:
            return RelevanceResult(sufficient=True, confidence=0.9)

        if "INSUFFICIENT" in verdict:
            aspects = [
                l.lstrip("- ").strip()
                for l in lines[1:]
                if l.startswith("-")
            ][:3]
            return RelevanceResult(sufficient=False, missing_aspects=aspects, confidence=0.9)

        # 無法解析 → fallback
        logger.warning(f"[RelevanceChecker] unexpected verdict line: {lines[0]!r}, fallback sufficient=True")
        return RelevanceResult(sufficient=True, confidence=0.4)
