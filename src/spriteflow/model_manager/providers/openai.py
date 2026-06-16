"""OpenAI Provider — 使用官方 Python SDK"""

from __future__ import annotations
import time
from .base import BaseProvider, ChannelConfig, TestResult


class OpenAIProvider(BaseProvider):
    """OpenAI 专用 Provider

    使用 openai 官方 Python SDK 测试连接和列出模型。
    支持 OpenAI 官方 API 及任意 OpenAI 兼容服务（如 Azure、本地 vLLM 等）。
    """

    @staticmethod
    def default_base_url() -> str:
        return "https://api.openai.com/v1"

    async def test_connection(self, config: ChannelConfig) -> TestResult:
        base_url = config.base_url or self.default_base_url()
        api_key = config.api_key

        if not api_key:
            return TestResult(success=False, message="未配置 API Key")

        try:
            from openai import OpenAI
        except ImportError:
            return TestResult(success=False, message="openai SDK 未安装，请执行: pip install openai")

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            t0 = time.time()
            models = client.models.list()
            latency = (time.time() - t0) * 1000
            count = len(models.data) if hasattr(models, 'data') else 0
            return TestResult(
                success=True,
                message=f"OpenAI SDK 连接成功，可用模型 {count} 个",
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            return TestResult(success=False, message=f"连接失败: {str(e)}")

    async def list_models(self, config: ChannelConfig) -> list[dict]:
        base_url = config.base_url or self.default_base_url()
        api_key = config.api_key

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url)
            models = client.models.list()
            if hasattr(models, 'data'):
                return [
                    {"id": m.id, "name": m.id}
                    for m in models.data
                ]
        except Exception:
            pass
        return []
