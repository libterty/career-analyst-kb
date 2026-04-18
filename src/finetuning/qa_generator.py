"""Phase 3 — QA Dataset Generator
從典籍切片自動生成一貫道專屬 QA 對，用於 Fine-tuning 或 Evaluation。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from langchain.schema import HumanMessage, SystemMessage
from loguru import logger

from ..core.llm_factory import build_llm
from ..ingestion.chunker import Chunk

# 用於指導 LLM 生成 QA 對的 Prompt 模板
# {num_pairs}: 每個切塊要生成幾組 QA
# {chunk_content}: 切塊的原文內容
_QA_GENERATION_PROMPT = """你是一貫道典籍的學術研究者。
請根據以下段落，生成 {num_pairs} 組高品質的問答對，用於訓練 AI 模型。

要求：
1. 問題應模擬真實道親可能提問的方式（可含一貫道專屬術語）
2. 答案應直接基於段落內容，不要添加段落以外的資訊
3. 每組 Q&A 獨立，格式嚴格按照 JSON 陣列輸出
4. 問題類型多樣：定義型、比較型、應用型

【段落內容】
{chunk_content}

請以此 JSON 格式輸出（只輸出 JSON，不要其他文字）：
[
  {{"question": "問題一", "answer": "答案一", "type": "definition"}},
  {{"question": "問題二", "answer": "答案二", "type": "comparison"}}
]"""


class QADatasetGenerator:
    """從切塊自動生成 QA 訓練資料集。

    用途：
        - Fine-tuning：用生成的 QA 對微調 LLM，提升一貫道問答準確度
        - Evaluation：用生成的 QA 對評測 RAG 系統的召回率與準確率
    """

    def __init__(self, model: Optional[str] = None) -> None:
        # temperature=0.7：較高溫度讓生成的問題更多樣化
        self._llm = build_llm(model=model, temperature=0.7, streaming=False)

    def generate_from_chunks(
        self,
        chunks: list[Chunk],
        num_pairs_per_chunk: int = 3,
        output_path: Optional[Path] = None,
    ) -> list[dict]:
        """從切塊列表批次生成 QA 訓練資料。

        Args:
            chunks:              要生成 QA 的切塊列表
            num_pairs_per_chunk: 每個切塊生成的 QA 對數（預設 3 對）
            output_path:         若指定，將結果儲存為 JSON 檔案

        Returns:
            QA 對列表，每筆包含 question、answer、type、source_chunk_id、source_file
        """
        all_pairs: list[dict] = []

        for i, chunk in enumerate(chunks):
            logger.info(f"Generating QA for chunk {i + 1}/{len(chunks)}")
            try:
                pairs = self._generate_for_chunk(chunk, num_pairs_per_chunk)
                # 為每筆 QA 附上來源切塊資訊（方便追溯）
                for pair in pairs:
                    pair["source_chunk_id"] = chunk.chunk_id
                    pair["source_file"] = chunk.metadata.get("filename", "")
                all_pairs.extend(pairs)
            except Exception as exc:
                # 單個切塊失敗不中斷整體流程
                logger.warning(f"Failed to generate QA for chunk {chunk.chunk_id}: {exc}")

        logger.success(f"Generated {len(all_pairs)} QA pairs from {len(chunks)} chunks")

        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_pairs, f, ensure_ascii=False, indent=2)
            logger.info(f"QA dataset saved to: {output_path}")

        return all_pairs

    def _generate_for_chunk(self, chunk: Chunk, num_pairs: int) -> list[dict]:
        """對單一切塊呼叫 LLM 生成 QA 對。

        Args:
            chunk:     要生成 QA 的切塊
            num_pairs: 要生成的 QA 對數量

        Returns:
            解析後的 QA 列表（dict 格式）

        Raises:
            json.JSONDecodeError: 若 LLM 輸出無法解析為有效 JSON
        """
        messages = [
            SystemMessage(content="你是專業的一貫道教育資料集建立者。"),
            HumanMessage(
                content=_QA_GENERATION_PROMPT.format(
                    num_pairs=num_pairs,
                    chunk_content=chunk.content[:2000],  # 截斷避免超出 context 長度
                )
            ),
        ]
        response = self._llm.invoke(messages)
        raw = response.content.strip()

        # 移除 LLM 可能多包的 Markdown code fence（```json ... ```）
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw)
