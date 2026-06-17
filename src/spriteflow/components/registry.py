"""
组件注册中心 — 统一管理所有 Component 实例

提供:
- 手动注册（由 __init__.py 负责）
- 按分类/schema 查询
- 凭据管理（持久化到 config DB，运行时从 .env 回退）
- 与 workflow model_registry 的桥接
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .base import Component, ComponentMeta

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """全局组件注册表"""

    _components: dict[str, Component] = {}
    _metas: dict[str, ComponentMeta] = {}
    _credentials: dict[str, dict[str, str]] = {}

    # ---- 组件注册 ----

    @classmethod
    def register(cls, component: Component) -> None:
        """注册一个组件"""
        cid = component.meta.component_id
        if cid in cls._components:
            logger.warning(f"Component {cid} already registered, overwriting")
        cls._components[cid] = component
        cls._metas[cid] = component.meta
        logger.info(
            f"[ComponentRegistry] registered: {cid} "
            f"({component.meta.category}/{component.meta.subcategory})"
        )

    @classmethod
    def get(cls, component_id: str) -> Optional[Component]:
        """获取组件实例"""
        return cls._components.get(component_id)

    @classmethod
    def get_meta(cls, component_id: str) -> Optional[ComponentMeta]:
        """获取组件元数据"""
        return cls._metas.get(component_id)

    @classmethod
    def list_all(cls) -> dict[str, ComponentMeta]:
        """列出所有组件的元数据"""
        return dict(cls._metas)

    @classmethod
    def list_components(cls) -> dict[str, Component]:
        """列出所有组件实例"""
        return dict(cls._components)

    @classmethod
    def list_by_category(cls, category: str) -> dict[str, ComponentMeta]:
        """按分类列出组件"""
        return {cid: m for cid, m in cls._metas.items() if m.category == category}

    @classmethod
    def list_schemas(cls) -> dict[str, dict]:
        """返回所有组件对应的 node-schema 字典"""
        return {cid: comp.to_node_schema() for cid, comp in cls._components.items()}

    @classmethod
    def get_categories(cls) -> set[str]:
        """获取所有分类"""
        return {m.category for m in cls._metas.values()}

    # ---- 凭据管理 ----

    @classmethod
    def get_credentials(cls, component_id: str) -> dict[str, str]:
        """获取组件的运行时凭据（DB 持久化值 + .env 回退）

        优先使用组件管理页配置的凭据，缺失字段回退到 .env 全局配置。
        """
        creds = dict(cls._credentials.get(component_id, {}))

        # 对缺失字段从 .env 回退（seedance 等组件依赖 ark_api_key）
        try:
            from ..config import settings as _s
        except Exception:
            _s = None

        if _s:
            if not creds.get("ark_api_key") and _s.ark_api_key:
                creds["ark_api_key"] = _s.ark_api_key
            if not creds.get("ark_base_url"):
                creds["ark_base_url"] = _s.ark_base_url

        return creds

    @classmethod
    def set_credentials(cls, component_id: str, credentials: dict[str, str]) -> None:
        """设置组件的凭据（运行时 + 持久化到 DB）"""
        cls._credentials[component_id] = credentials

    @classmethod
    def load_credentials_from_db(cls, db) -> None:
        """从 config DB 恢复所有组件凭据到内存"""
        import asyncio
        import json as _json

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # 不在异步上下文中

        async def _load():
            try:
                raw = await db.get_configs_by_prefix("component_credential:")
                count = 0
                for cid, json_str in raw.items():
                    try:
                        creds = _json.loads(json_str) if isinstance(json_str, str) else json_str
                        if isinstance(creds, dict):
                            cls._credentials[cid] = creds
                            count += 1
                    except _json.JSONDecodeError:
                        logger.warning(f"[ComponentRegistry] 凭据 JSON 解析失败: {cid}")
                if count:
                    logger.info(f"[ComponentRegistry] 从 DB 恢复 {count} 个组件的凭据")
            except Exception as e:
                logger.warning(f"[ComponentRegistry] 加载组件凭据失败: {e}")

        # 创建任务（不阻塞）
        loop.create_task(_load())

    @classmethod
    def mask_credentials(cls, creds: dict[str, str]) -> dict[str, str]:
        """遮蔽凭据中的敏感字段"""
        masked = {}
        for k, v in creds.items():
            if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                masked[k] = "****" + v[-4:] if len(v) > 4 else "****"
            else:
                masked[k] = v
        return masked
