"""集中定義所有 Domain 例外。

將例外集中管理，避免各模組互相引入造成循環依賴。
"""
from __future__ import annotations


class SecurityError(Exception):
    """請求被安全層封鎖時拋出。"""


class IngestionError(Exception):
    """文件處理失敗時拋出。"""


class AuthenticationError(Exception):
    """認證或授權失敗時拋出。"""


class ProviderNotFoundError(ValueError):
    """找不到指定的 LLM/Embedding Provider 時拋出。"""


class DocumentNotFoundError(Exception):
    """文件不存在時拋出。"""
