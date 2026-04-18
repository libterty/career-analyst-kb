"""LLM Provider Registry（Registry Pattern + OCP）。

取代原本的 if/elif 工廠函式：
    - 新增 Provider 只需新增一個檔案並呼叫 registry.register()
    - 不需修改任何現有程式碼（Open/Closed Principle）

使用方式：
    registry = build_default_registry(settings)
    provider = registry.get("ollama")
    llm = provider.build_llm()
"""
from __future__ import annotations

from src.core.exceptions import ProviderNotFoundError
from src.core.interfaces.llm import ILLMProvider


class LLMProviderRegistry:
    """LLM Provider 登錄表。

    保存 provider 名稱 → 策略實例的對應，
    支援執行時動態添加 provider。
    """

    def __init__(self) -> None:
        self._providers: dict[str, ILLMProvider] = {}

    def register(self, name: str, provider: ILLMProvider) -> None:
        """註冊一個 Provider。

        Args:
            name:     Provider 名稱（不分大小寫）
            provider: 實作 ILLMProvider 的策略實例
        """
        self._providers[name.lower()] = provider

    def get(self, name: str) -> ILLMProvider:
        """取得指定 Provider。

        Args:
            name: Provider 名稱

        Raises:
            ProviderNotFoundError: 找不到指定 Provider
        """
        provider = self._providers.get(name.lower())
        if provider is None:
            available = ", ".join(self._providers.keys()) or "(none registered)"
            raise ProviderNotFoundError(
                f"Unknown provider '{name}'. Available: {available}"
            )
        return provider

    @property
    def available_providers(self) -> list[str]:
        """回傳所有已註冊的 Provider 名稱列表。"""
        return list(self._providers.keys())
