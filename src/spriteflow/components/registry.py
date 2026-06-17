"""
组件注册中心 — 统一管理所有 Component 实例

提供:
- 手动注册（由 __init__.py 负责）
- 按分类/schema 查询
- 与 workflow model_registry 的桥接
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import Component, ComponentMeta

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """全局组件注册表"""

    _components: dict[str, Component] = {}
    _metas: dict[str, ComponentMeta] = {}

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
