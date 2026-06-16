"""Provider 基类 — 定义通道 provider 的抽象接口"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChannelConfig:
    """通道配置"""
    name: str
    provider_type: str
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class TestResult:
    """连接测试结果"""
    success: bool
    message: str
    latency_ms: float | None = None


class BaseProvider(ABC):
    """Provider 基类 — 各 provider 实现通道连接测试、模型列表等功能"""

    @abstractmethod
    async def test_connection(self, config: ChannelConfig) -> TestResult:
        """测试通道连接"""
        ...

    @abstractmethod
    async def list_models(self, config: ChannelConfig) -> list[dict]:
        """列出 Provider 上的可用模型"""
        ...

    @staticmethod
    @abstractmethod
    def default_base_url() -> str:
        """返回该 provider 的默认 base_url"""
        ...
