"""Replicate Provider — 使用官方 Python SDK"""

from __future__ import annotations
import time
from .base import BaseProvider, ChannelConfig, TestResult


class ReplicateProvider(BaseProvider):
    """Replicate 专用 Provider

    使用 replicate 官方 Python SDK 测试连接和列出模型。
    SDK 使用 API Key 直接鉴权，无需 base_url。
    """

    @staticmethod
    def default_base_url() -> str:
        return "https://api.replicate.com/v1"

    async def test_connection(self, config: ChannelConfig) -> TestResult:
        api_key = config.api_key

        if not api_key:
            return TestResult(success=False, message="未配置 API Key（Replicate API Token）")

        try:
            import replicate  # type: ignore
        except ImportError:
            return TestResult(success=False, message="replicate SDK 未安装，请执行: pip install replicate")

        try:
            client = replicate.Client(api_token=api_key)
            t0 = time.time()
            # 获取模型列表验证连接
            models = client.models.list()
            latency = (time.time() - t0) * 1000

            # models 是一个迭代器，取一页来判断
            count = 0
            for _ in models:
                count += 1
                if count >= 10:
                    break

            return TestResult(
                success=True,
                message=f"Replicate SDK 连接成功，可用模型 {count}+ 个",
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            return TestResult(success=False, message=f"连接失败: {str(e)}")

    async def list_models(self, config: ChannelConfig) -> list[dict]:
        api_key = config.api_key
        try:
            import replicate
            client = replicate.Client(api_token=api_key)
            models = []
            for m in client.models.list():
                models.append({"id": f"{m.owner}/{m.name}", "name": m.name or m.description or m.owner})
                if len(models) >= 50:
                    break
            return models
        except Exception:
            return []
