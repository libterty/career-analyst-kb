"""Phase 1 — Smart Chunker
策略：語意段落優先 → 固定 Token 大小 fallback，保留段落結構。
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Optional

import tiktoken
from langchain.text_splitter import RecursiveCharacterTextSplitter
from loguru import logger

from .pdf_parser import ParsedDocument


@dataclass
class Chunk:
    """單一文本切塊的資料結構。

    Attributes:
        chunk_id: 唯一識別碼，格式為 {doc_hash}-{序號}
        doc_hash: 所屬文件的指紋，用於追溯來源
        source: 來源文件路徑
        content: 該切塊的純文字內容
        page_hint: 大約對應的頁碼（可選）
        section: 偵測到的章節名稱（如「第三章」）
        token_count: 該切塊的 token 數量
        metadata: 附加資訊（檔名、切塊序號等）
    """
    chunk_id: str
    doc_hash: str
    source: str
    content: str
    page_hint: Optional[int] = None
    section: str = ""
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


# 章節分隔標記，切塊時優先在這些邊界切割
# 越前面的分隔符優先級越高（先嘗試章節邊界，最後才切字元）
_DOCUMENT_SEPARATORS = [
    r"\n第[一二三四五六七八九十百千]+章",   # 第X章
    r"\n第[一二三四五六七八九十百千]+節",   # 第X節
    r"\n[（(]\d+[)）]",                    # (1) 條目
    r"\n\d+\.",                            # 1. 條目
    r"\n[•·●]\s",                          # bullet points
    "\n\n\n",
    "\n\n",
    "\n",
    " ",
    "",
]


class SmartChunker:
    """智慧文本切塊器。

    先嘗試依語意邊界切割（章節、段落），
    再以 Token 上限保證每塊不超過 max_tokens。
    chunk_overlap 確保相鄰切塊有重疊，避免跨塊的重要資訊被截斷。
    """

    def __init__(
        self,
        max_tokens: int = 512,
        chunk_overlap: int = 64,
        model_encoding: str = "cl100k_base",
    ) -> None:
        """初始化切塊器。

        Args:
            max_tokens: 每塊最大 token 數（預設 512）
            chunk_overlap: 相鄰塊的重疊 token 數（預設 64）
            model_encoding: tiktoken 編碼名稱（cl100k_base 適用 GPT-4/nomic-embed）
        """
        self.max_tokens = max_tokens
        self.chunk_overlap = chunk_overlap
        self._enc = tiktoken.get_encoding(model_encoding)
        self._splitter = RecursiveCharacterTextSplitter(
            separators=_DOCUMENT_SEPARATORS,
            chunk_size=max_tokens,        # length_function 已是 token 計算，直接用 max_tokens
            chunk_overlap=chunk_overlap,
            length_function=self._token_len,  # 以 token 數而非字元數計算長度
            is_separator_regex=True,
        )

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """將解析後的文件切割成多個 Chunk。

        Args:
            doc: 已解析的文件物件

        Returns:
            切塊列表，每塊含 chunk_id、content、section 等資訊
        """
        raw_chunks = self._splitter.split_text(doc.content)
        chunks: list[Chunk] = []
        for idx, text in enumerate(raw_chunks):
            if not text.strip():
                continue  # 跳過空白塊
            chunk_id = f"{doc.doc_hash}-{idx:04d}"  # 格式：指紋-0000
            page_number = self._find_page_number(text, doc)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_hash=doc.doc_hash,
                    source=doc.source,
                    content=text.strip(),
                    page_hint=page_number,
                    section=self._extract_section(text),  # 嘗試識別章節名
                    token_count=self._token_len(text),
                    metadata={
                        "filename": doc.metadata.get("filename", ""),
                        "chunk_index": idx,
                        "total_chunks": len(raw_chunks),
                    },
                )
            )
        logger.info(f"Chunked '{doc.metadata.get('filename')}' → {len(chunks)} chunks")
        return chunks

    # ------------------------------------------------------------------

    def _token_len(self, text: str) -> int:
        """計算文字的 token 數量（使用 tiktoken）。"""
        return len(self._enc.encode(text))
    
    @staticmethod
    def _find_page_number(chunk_text: str, doc: ParsedDocument) -> int | None:
        """根據 page_breaks 定位 chunk 文字對應的頁碼（1-based）。

        使用 bisect 在 page_breaks 中找到 chunk_text 第一次出現位置所在的頁。
        若文件未提供 page_breaks（非 PDF），回傳 None。
        """
        if not doc.page_breaks:
            return None
        # 找 chunk 在整份文件 content 中的起始位置
        pos = doc.content.find(chunk_text[:50])  # 用前 50 字定位，避免全文搜尋太慢
        if pos < 0:
            return None
        # bisect_right 找到第一個 > pos 的頁起始索引，再減 1 得到所在頁索引
        page_idx = bisect.bisect_right(doc.page_breaks, pos) - 1
        return max(0, page_idx) + 1  # 轉為 1-based

    @staticmethod
    def _extract_section(text: str) -> str:
        """從切塊開頭擷取章節名稱。

        支援 Markdown 標題（# ~ ######）及中文章節（第X章、第X節）。
        只看前 150 字是為了效能，章節標題通常在段落開頭。
        """
        head = text[:150]
        # Markdown 標題：取標題文字（去除 # 前綴）
        m = re.match(r"^#{1,6}\s+(.+)", head.lstrip())
        if m:
            return m.group(1).strip()
        # 中文章節
        m = re.search(r"第[一二三四五六七八九十百千\d]+[章節]", head)
        return m.group(0) if m else ""
