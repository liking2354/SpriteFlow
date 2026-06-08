"""能力路由器 — 读 routing.yaml，cap → provider 映射 + 回退链（含重试）"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from .base import Provider, Capability, Credential
from ..config import settings

logger = logging.getLogger("spriteflow.router")


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
                self._credentials.setdefault(provider_name, os.environ.get(env_var, ""))
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
        每个 provider 支持最多 N 次重试（通过 settings.generation_retry_count 配置）。
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
        retry_count = max(1, settings.generation_retry_count)
        retry_delay = max(0, settings.generation_retry_delay_sec)

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

            # 对每个 provider 支持重试（含首次尝试 = 1 + N 次重试）
            for attempt in range(1, retry_count + 1):
                try:
                    result = await provider.invoke(capability, payload, cred)
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < retry_count:
                        logger.warning(
                            "[router] provider=%s capability=%s attempt=%d/%d failed: %s. retrying in %.1fs...",
                            name, cap_name, attempt, retry_count, e, retry_delay,
                        )
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(
                            "[router] provider=%s capability=%s exhausted %d attempt(s). last error: %s",
                            name, cap_name, retry_count, e,
                        )
                        break  # 该 provider 已耗尽，尝试下一个（回退链）

        raise RuntimeError(
            f"能力 '{cap_name}' 所有 provider 均调用失败（已重试 {retry_count} 次）。最后错误: {last_error}"
        )

    def get_routes(self) -> dict[str, str]:
        """获取当前路由表"""
        return dict(self._routes)

    def get_fallbacks(self) -> dict[str, list[str]]:
        """获取当前回退链"""
        return {k: list(v) for k, v in self._fallbacks.items()}

    def get_provider_configs(self) -> dict[str, dict[str, object]]:
        """获取各 provider 当前配置（model / base_url / api_key 状态）"""
        result: dict[str, dict[str, object]] = {}
        for name, p in self._providers.items():
            cfg: dict[str, object] = {
                "name": name,
                "capabilities": [c.value for c in p.capabilities],
                "api_key_configured": bool(self._credentials.get(name)),
            }
            # 尝试读取 model / base_url（如果 provider 暴露了这些属性）
            if hasattr(p, "_model"):
                cfg["model"] = getattr(p, "_model")
            if hasattr(p, "_base_url"):
                cfg["base_url"] = getattr(p, "_base_url")
            result[name] = cfg
        return result

    def update_route(self, capability: str, provider_name: str) -> None:
        """更新路由映射"""
        self._routes[capability] = provider_name

    def update_fallback(self, capability: str, fallback_list: list[str]) -> None:
        """更新回退链"""
        self._fallbacks[capability] = list(fallback_list)

    def update_credential(self, provider_name: str, api_key: str) -> None:
        """运行时更新凭证"""
        self._credentials[provider_name] = api_key
        # 同步更新 provider 实例的 api_key（如果支持）
        p = self._providers.get(provider_name)
        if p is not None and hasattr(p, "_api_key"):
            setattr(p, "_api_key", api_key)

    def update_provider_model(self, provider_name: str, model: str) -> None:
        """运行时更新 provider 模型"""
        p = self._providers.get(provider_name)
        if p is not None and hasattr(p, "_model"):
            setattr(p, "_model", model)

    def update_provider_base_url(self, provider_name: str, base_url: str) -> None:
        """运行时更新 provider 端点"""
        p = self._providers.get(provider_name)
        if p is not None and hasattr(p, "_base_url"):
            setattr(p, "_base_url", base_url.rstrip("/"))

    def persist_routing(self) -> None:
        """将当前路由/回退链写回 routing.yaml"""
        import yaml as _yaml

        config: dict[str, object] = {}
        if self._config_path.exists():
            with open(self._config_path) as f:
                config = _yaml.safe_load(f) or {}

        config["routes"] = dict(self._routes)
        config["fallback"] = {k: list(v) for k, v in self._fallbacks.items()}

        # 保留已有的 credentials 不覆盖
        if "credentials" not in config:
            config["credentials"] = {}

        with open(self._config_path, "w") as f:
            _yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        logger.info("[router] 路由配置已持久化到 %s", self._config_path)

    def reload(self) -> None:
        """从 routing.yaml 重新加载路由"""
        self._load_config()
        logger.info("[router] 路由配置已从 %s 重新加载", self._config_path)
