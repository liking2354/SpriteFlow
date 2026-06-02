"""能力路由器 — 读 routing.yaml，cap → provider 映射 + 回退链"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .base import Provider, Capability, Credential
from ..config import settings


class CapabilityRouter:
    """能力路由器

    职责：
    1. 读取路由配置（routing.yaml）
    2. 按 capability 查找对应 provider
    3. 主 provider 失败时走回退链
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        providers: dict[str, Provider] | None = None,
        credentials: dict[str, str] | None = None,
    ) -> None:
        self._config_path = Path(config_path) if config_path else settings.routing_config
        self._providers: dict[str, Provider] = providers or {}
        self._credentials: dict[str, str] = credentials or {}
        self._routes: dict[str, str] = {}
        self._fallbacks: dict[str, list[str]] = {}

        self._load_config()

    def _load_config(self) -> None:
        """加载路由配置"""
        if not self._config_path.exists():
            # 默认路由
            self._routes = {
                "text2img": "seedream",
                "img2img": "seedream",
                "multi_image_fusion": "seedream",
                "sequential_images": "seedream",
                "remove_bg": "rembg",
            }
            return

        with open(self._config_path) as f:
            config = yaml.safe_load(f) or {}

        self._routes = config.get("routes", {})
        self._fallbacks = config.get("fallback", {})

        # 从环境变量解析凭证
        cred_config = config.get("credentials", {})
        for provider_name, value in cred_config.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                self._credentials.setdefault(provider_name, "")
            else:
                self._credentials.setdefault(provider_name, str(value))

    def register_provider(self, provider: Provider) -> None:
        """注册 provider"""
        self._providers[provider.name] = provider

    def set_credential(self, provider_name: str, api_key: str) -> None:
        """设置凭证"""
        self._credentials[provider_name] = api_key

    async def route(
        self,
        capability: Capability,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """路由能力调用到对应 provider

        主 provider 失败时自动尝试回退链。
        """
        cap_name = capability.value
        provider_name = self._routes.get(cap_name)

        if not provider_name:
            raise ValueError(f"未配置能力 '{cap_name}' 的路由")

        # 构建尝试顺序：主 provider + 回退链
        try_list = [provider_name]
        if cap_name in self._fallbacks:
            try_list.extend(self._fallbacks[cap_name])

        last_error: Exception | None = None
        for name in try_list:
            provider = self._providers.get(name)
            if not provider:
                continue

            if not provider.supports(capability):
                continue

            cred = Credential(
                provider_name=name,
                api_key=self._credentials.get(name, ""),
            )

            try:
                result = await provider.invoke(capability, payload, cred)
                return result
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"能力 '{cap_name}' 所有 provider 均调用失败。最后错误: {last_error}"
        )

    def get_routes(self) -> dict[str, str]:
        """获取当前路由表"""
        return dict(self._routes)

    def update_route(self, capability: str, provider_name: str) -> None:
        """更新路由映射"""
        self._routes[capability] = provider_name
