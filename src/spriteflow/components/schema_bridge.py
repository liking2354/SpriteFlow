"""
Schema 桥接 — 将 ComponentMeta 转换为 workflow 兼容的 NodeSchema 格式
"""

from __future__ import annotations

from .base import Component


def component_to_node_schema(component: Component) -> dict:
    """将 Component 转换为 workflow node-schemas 格式

    返回的字典结构对应 /api/workflow/{id}/node-schemas 中
    categories.{category}.models.{model_id} 的格式
    """
    meta = component.meta

    # 构建 input_schema（前端表单结构）
    input_schema = {
        "schemas": {
            "input_data": {
                "properties": meta.input_schema,
                "required": meta.input_required,
            }
        }
    }

    return {
        "name": meta.display_name,
        "input_schema": input_schema,
        # 附加组件元信息
        "_component": {
            "component_id": meta.component_id,
            "version": meta.version,
            "description": meta.description,
            "category": meta.category,
            "subcategory": meta.subcategory,
            "output_type": meta.output_type,
            "credential_schema": meta.credential_schema,
        },
    }


def inject_component_schemas(base_schemas: dict) -> dict:
    """将已注册的组件 schemas 注入到 base_schemas 中

    Args:
        base_schemas: 从 _base_schemas() 或 get_node_schemas() 获取的 schemas 字典

    Returns:
        注入后的 schemas（直接修改传入的字典）
    """
    from .registry import ComponentRegistry

    for comp_id, comp in ComponentRegistry.list_components().items():
        meta = comp.meta
        cat_key = meta.category

        # 确保分类存在
        if cat_key not in base_schemas.get("categories", {}):
            if "categories" not in base_schemas:
                base_schemas["categories"] = {}
            base_schemas["categories"][cat_key] = {
                "name": f"{meta.category.capitalize()} Components",
                "models": {},
            }

        cat = base_schemas["categories"][cat_key]
        node_schema = comp.to_node_schema()
        # 添加 subcategory 信息
        node_schema["subcategory"] = meta.subcategory
        cat["models"][comp_id] = node_schema

    return base_schemas
