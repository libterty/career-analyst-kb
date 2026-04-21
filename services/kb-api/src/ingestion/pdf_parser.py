"""Phase 1 — Document Parser
支援 PDF / DOCX / TXT，含中文 OCR fallback。
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber
import pytesseract
from loguru import logger
from PIL import Image
from pypdf import PdfReader
from unstructured.partition.auto import partition


@dataclass
class ParsedDocument:
    """解析後的文件資料結構。

    Attributes:
        source:      文件來源路徑
        content:     提取出的純文字內容（所有頁合併）
        pages:       文件總頁數
        language:    文件語言（預設繁體中文）
        doc_hash:    文件內容的 SHA-256 前 16 碼，用於去重判斷
        metadata:    附加資訊（檔名、使用的解析器等）
        page_texts:  各頁文字列表（索引 0 對應第 1 頁），供 chunker 計算頁碼用
        page_breaks: 各頁在 content 中的起始字元偏移（用於 binary search 定位頁碼）
    """
    source: str
    content: str
    pages: int
    language: str = "zh-TW"
    doc_hash: str = field(default="")
    metadata: dict = field(default_factory=dict)
    page_texts: list[str] = field(default_factory=list)
    page_breaks: list[int] = field(default_factory=list)  # len == pages

    def __post_init__(self) -> None:
        # 若未提供 doc_hash，自動依內容計算 SHA-256 指紋（前 16 碼）
        if not self.doc_hash:
            self.doc_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]


class DocumentParser:
    """多格式文件解析器，優先使用 pdfplumber，失敗時自動 OCR。"""

    SUPPORTED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt", ".pptx", ".ppt",
                          ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
                          ".md", ".markdown"}

    def parse(self, path: str | Path) -> ParsedDocument:
        """解析指定路徑的文件，回傳 ParsedDocument。"""
        path = Path(path)
        if path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported file type: {path.suffix}")

        logger.info(f"Parsing document: {path.name}")

        # PDF 使用專屬解析流程（含 OCR fallback）
        if path.suffix.lower() == ".pdf":
            return self._parse_pdf(path)
        # 圖片格式使用 OCR 直接提取文字
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
            return self._parse_image(path)
        # Markdown 格式直接讀取純文字
        if path.suffix.lower() in {".md", ".markdown"}:
            return self._parse_markdown(path)
        # 其他格式（DOCX、TXT、PPTX）使用通用解析器
        return self._parse_generic(path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_pdf(self, path: Path) -> ParsedDocument:
        """解析 PDF 文件。

        優先使用 pdfplumber 提取文字；若某頁文字過少（掃描版 PDF），
        自動對該頁進行 OCR 識別。若 pdfplumber 整體失敗，則 fallback 到 pypdf。
        """
        texts: list[str] = []
        page_count = 0

        try:
            with pdfplumber.open(path) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if len(text.strip()) < 20:
                        # 文字少於 20 字，判斷為掃描頁，改用 OCR
                        text = self._ocr_page(page)
                    texts.append(text)
        except Exception as exc:
            logger.warning(f"pdfplumber failed ({exc}), falling back to pypdf")
            texts, page_count = self._parse_pdf_fallback(path)

        # 保留所有頁文字（含空白頁，以維持頁碼對應正確性）
        # page_breaks 記錄每頁在合併 content 中的起始字元偏移
        page_breaks: list[int] = []
        parts: list[str] = []
        offset = 0
        for t in texts:
            page_breaks.append(offset)
            parts.append(t)
            offset += len(t) + 2  # +2 for "\n\n" separator

        content = "\n\n".join(parts)
        return ParsedDocument(
            source=path.name,
            content=content,
            pages=page_count,
            metadata={"filename": path.name, "parser": "pdfplumber"},
            page_texts=texts,
            page_breaks=page_breaks,
        )

    def _parse_pdf_fallback(self, path: Path) -> tuple[list[str], int]:
        """使用 pypdf 作為備用 PDF 解析器（不支援 OCR）。"""
        reader = PdfReader(str(path))
        texts = [page.extract_text() or "" for page in reader.pages]
        return texts, len(reader.pages)

    def _ocr_page(self, page) -> str:
        """對單一 PDF 頁面進行 OCR 文字識別。

        解析度設為 300 DPI 以確保中文字的識別準確率。
        同時支援繁體中文（chi_tra）與英文（eng）。
        """
        try:
            img = page.to_image(resolution=300).original
            if not isinstance(img, Image.Image):
                img = Image.fromarray(img)
            return pytesseract.image_to_string(img, lang="chi_tra+eng")
        except Exception as exc:
            logger.debug(f"OCR failed for page: {exc}")
            return ""

    def _parse_image(self, path: Path) -> ParsedDocument:
        """使用 Tesseract OCR 解析圖片文件，提取其中的文字。

        同時支援繁體中文（chi_tra）與英文（eng）。
        若 OCR 未提取到任何文字，記錄警告並回傳空內容。
        """
        try:
            img = Image.open(path)
            content = pytesseract.image_to_string(img, lang="chi_tra+eng")
            content = content.strip()
        except Exception as exc:
            logger.warning(f"Image OCR failed for {path.name}: {exc}")
            content = ""

        if not content:
            logger.warning(f"No text extracted from image: {path.name}")

        return ParsedDocument(
            source=path.name,
            content=content,
            pages=1,
            metadata={"filename": path.name, "parser": "tesseract-ocr"},
        )

    def _parse_markdown(self, path: Path) -> ParsedDocument:
        """直接讀取 Markdown 文件，保留原始文字內容（含 # 標題等語法）。

        Markdown 本身即為可讀純文字，直接讀取後可正確進行切塊與向量化。
        標題符號（#）可作為章節邊界，有助於 chunker 分段。
        """
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")

        return ParsedDocument(
            source=path.name,
            content=content.strip(),
            pages=1,
            metadata={"filename": path.name, "parser": "markdown"},
        )

    def _parse_generic(self, path: Path) -> ParsedDocument:
        """使用 unstructured 函式庫解析 DOCX、TXT 等非 PDF 格式。

        unstructured 會自動判斷文件結構（標題、段落、表格等）並提取文字。
        Title 元素轉為 Markdown 標題（## heading），使 SmartChunker 能識別章節邊界
        並正確填入 section 欄位，改善向量檢索的段落定位準確度。
        """
        elements = partition(filename=str(path))
        parts: list[str] = []
        for el in elements:
            category = getattr(el, "category", None) or type(el).__name__
            text = str(el).strip()
            if not text:
                continue
            if category == "Title":
                parts.append(f"## {text}")
            else:
                parts.append(text)
        content = "\n\n".join(parts)
        return ParsedDocument(
            source=path.name,
            content=content,
            pages=1,
            metadata={"filename": path.name, "parser": "unstructured"},
        )
