"""Ollama Provider — 使用官方 Python SDK"""

from __future__ import annotations
import time
from .base import BaseProvider, ChannelConfig, TestResult


class OllamaProvider(BaseProvider):
    """Ollama 专用 Provider

    使用 ollama 官方 Python SDK 测试连接和列出本地模型。
    默认地址 http://localhost:11434。
    """

    @staticmethod
    def default_base_url() -> str:
        return "http://localhost:11434"

    async def test_connection(self, config: ChannelConfig) -> TestResult:
        base_url = config.base_url or self.default_base_url()

        try:
            import ollama  # type: ignore
        except ImportError:
            return TestResult(success=False, message="ollama SDK 未安装，请执行: pip install ollama")

        try:
            client = ollama.Client(host=base_url)
            t0 = time.time()
            resp = client.list()
            latency = (time.time() - t0) * 1000

            models = resp.get("models", []) if isinstance(resp, dict) else []
            count = len(models)
            names = ", ".join(m.get("name", "") for m in models[:5])

            return TestResult(
                success=True,
                message=f"Ollama 连接成功，本地 {count} 个模型" + (f"（{names}）" if names else ""),
                latency_ms=round(latency, 1),
            )
        except Exception as e:
            msg = str(e)
            if "Connection refused" in msg or "ConnectionError" in msg:
                return TestResult(success=False, message=f"无法连接到 {base_url}，请确认 Ollama 服务已启动")
            return TestResult(success=False, message=f"连接失败: {msg}")

    async def list_models(self, config: ChannelConfig) -> list[dict]:
        base_url = config.base_url or self.default_base_url()
        try:
            import ollama
            client = ollama.Client(host=base_url)
            resp = client.list()
            models = resp.get("models", []) if isinstance(resp, dict) else []
            return [
                {"id": m.get("name", ""), "name": m.get("name", "")}
                for m in models
            ]
        except Exception:
            return []
