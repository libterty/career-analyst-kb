"""ParsedDocument 值物件。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedDocument:
    """已解析文件的值物件（不可變）。

    Attributes:
        source:    來源文件路徑或名稱
        content:   完整文字內容
        pages:     文件總頁數
        language:  文件語言（預設繁體中文）
        doc_hash:  SHA-256 指紋（前 16 碼），用於去重
        metadata:  其他擴充 metadata
    """

    source: str
    content: str
    pages: int
    language: str = "zh-TW"
    doc_hash: str = field(default="")
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # frozen=True 需透過 object.__setattr__ 設定預設值
        if not self.doc_hash:
            computed = hashlib.sha256(self.content.encode()).hexdigest()[:16]
            object.__setattr__(self, "doc_hash", computed)
