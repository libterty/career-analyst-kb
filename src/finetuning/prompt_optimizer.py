"""Phase 3 — Prompt Optimizer
注入一貫道術語定義以提升 LLM 理解準確度。
預留 LoRA fine-tuning 接口。

實作 IQueryEnhancer 介面，ChatService 透過介面依賴，不直接引入此類別。
"""
from __future__ import annotations

from src.core.interfaces.query_enhancer import IQueryEnhancer
from .glossary import ALIAS_MAP, YIGUANDAO_GLOSSARY

# 術語補充說明的前言模板，插入 System Prompt 前
_GLOSSARY_PREAMBLE = """【一貫道術語補充說明】
以下為本次問題中可能涉及的一貫道專屬術語定義，請參考以回答：
{definitions}
"""


class PromptOptimizer(IQueryEnhancer):
    """查詢優化器，兩層優化策略：

    1. Query Normalization（查詢正規化）
       將俗稱別名替換為典籍中使用的標準術語。
       例：「老母」→「無極老母」，確保能匹配到典籍原文。

    2. Context Injection（術語定義注入）
       偵測問題中出現的一貫道術語，在 System Prompt 前附上術語定義，
       幫助 LLM 以正確的教義理解回答問題。
    """

    def enhance_query(self, query: str) -> str:
        """正規化查詢文字，將俗稱替換為標準術語。

        Args:
            query: 使用者的原始問題

        Returns:
            替換別名後的標準化查詢
        """
        for alias, canonical in ALIAS_MAP.items():
            query = query.replace(alias, canonical)
        return query

    def build_glossary_context(self, query: str) -> str:
        """擷取查詢中出現的術語並格式化為補充說明文字。

        Args:
            query: 已正規化的查詢文字

        Returns:
            術語補充說明字串（若無相關術語則回傳空字串）
        """
        relevant: dict[str, str] = {}
        # 掃描術語表，找出查詢中出現的術語
        for term, definition in YIGUANDAO_GLOSSARY.items():
            if term in query:
                relevant[term] = definition

        if not relevant:
            return ""

        lines = [f"• {term}：{defn}" for term, defn in relevant.items()]
        return _GLOSSARY_PREAMBLE.format(definitions="\n".join(lines))

    # ------------------------------------------------------------------
    # LoRA Fine-tuning Interface（預留接口）
    # ------------------------------------------------------------------

    @staticmethod
    def load_finetuned_adapter(adapter_path: str) -> None:
        """預留接口：載入 LoRA Fine-tuning Adapter。

        LoRA（Low-Rank Adaptation）可在不修改基礎模型的情況下，
        用少量參數針對一貫道問答任務進行微調，提升回答準確度。

        使用方式（需要 peft 函式庫）：
            from peft import PeftModel
            base_model = AutoModelForCausalLM.from_pretrained(base_model_id)
            model = PeftModel.from_pretrained(base_model, adapter_path)
        """
        raise NotImplementedError(
            "LoRA adapter loading not yet implemented. "
            "See src/finetuning/lora_trainer.py for training pipeline."
        )
