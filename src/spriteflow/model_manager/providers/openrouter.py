"""OpenRouter Provider — 支持官方 SDK 和 OpenAI 兼容 API"""

from __future__ import annotations
import time
import httpx
from .base import BaseProvider, ChannelConfig, TestResult


class OpenRouterProvider(BaseProvider):
    """OpenRouter 专用 Provider

    - 优先尝试使用 openrouter SDK（pip install openrouter）
    - 降级为 OpenAI 兼容 API（base_url: https://openrouter.ai/api/v1）
    """

    @staticmethod
    def default_base_url() -> str:
        return "https://openrouter.ai/api/v1"

    async def test_connection(self, config: ChannelConfig) -> TestResult:
        base_url = config.base_url or self.default_base_url()
        api_key = config.api_key

        if not api_key:
            return TestResult(success=False, message="未配置 API Key")

        # 尝试使用 openrouter SDK
        try:
            from openrouter import OpenRouter
            client = OpenRouter(api_key=api_key)
            t0 = time.time()
            # 获取模型列表来验证连接
            models = client.models.list()
            latency = (time.time() - t0) * 1000
            count = len(models.data) if hasattr(models, 'data') else 0
            return TestResult(
                success=True,
                message=f"OpenRouter SDK 连接成功，可用模型 {count} 个",
                latency_ms=round(latency, 1),
            )
        except ImportError:
            pass  # SDK 未安装，使用 HTTP 方式
        except Exception as e:
            pass  # SDK 方式失败，尝试 HTTP

        # 降级：使用 OpenAI 兼容 API
        return await self._test_via_http(base_url, api_key)

    async def _test_via_http(self, base_url: str, api_key: str) -> TestResult:
        """通过 HTTP 请求测试连接（OpenAI 兼容模式）"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://spriteflow.app",
            "X-Title": "SpriteFlow",
        }
        try:
            t0 = time.time()
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    base_url.rstrip("/") + "/models",
                    headers=headers,
                )
            latency = (time.time() - t0) * 1000
            if resp.status_code < 500:
                try:
                    data = resp.json()
                    model_count = len(data.get("data", data)) if isinstance(data, dict) else len(data)
                    return TestResult(
                        success=True,
                        message=f"连接成功 (HTTP {resp.status_code})，{model_count} 个模型可用",
                        latency_ms=round(latency, 1),
                    )
                except Exception:
                    return TestResult(
                        success=True,
                        message=f"连接成功 (HTTP {resp.status_code})",
                        latency_ms=round(latency, 1),
                    )
            else:
                return TestResult(
                    success=False,
                    message=f"服务器返回 {resp.status_code}: {resp.text[:200]}",
                    latency_ms=round(latency, 1),
                )
        except httpx.TimeoutException:
            return TestResult(success=False, message="连接超时（15s）")
        except Exception as e:
            return TestResult(success=False, message=f"连接失败: {str(e)}")

    async def list_models(self, config: ChannelConfig) -> list[dict]:
        base_url = config.base_url or self.default_base_url()
        api_key = config.api_key

        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    base_url.rstrip("/") + "/models",
                    headers=headers,
                )
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", data) if isinstance(data, dict) else data
                if isinstance(models, list):
                    return [
                        {"id": m.get("id", ""), "name": m.get("name", m.get("id", ""))}
                        for m in models
                    ]
        except Exception:
            pass
        return []
