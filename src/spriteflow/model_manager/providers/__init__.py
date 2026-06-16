"""Provider 注册中心 — 管理各通道 provider 实现"""

from .base import BaseProvider, ChannelConfig, TestResult
from .openai import OpenAIProvider
from .openrouter import OpenRouterProvider
from .replicate import ReplicateProvider
from .ollama import OllamaProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "openai": OpenAIProvider,
    "openrouter": OpenRouterProvider,
    "replicate": ReplicateProvider,
    "ollama": OllamaProvider,
}


def get_provider(provider_type: str) -> BaseProvider | None:
    """获取 provider 实例，无专用实现则返回 None"""
    cls = PROVIDER_REGISTRY.get(provider_type)
    return cls() if cls else None


__all__ = ["BaseProvider", "ChannelConfig", "TestResult", "get_provider", "PROVIDER_REGISTRY"]
