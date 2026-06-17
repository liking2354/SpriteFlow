"""
Schema 桥接 — 将 ComponentMeta 转换为 workflow 兼容的 NodeSchema 格式
"""

from __future__ import annotations

from .base import Component


def _output_type_to_functional_category(output_type: str) -> str | None:
    """根据 output_type 推导对应的功能分类 key

    前端节点组件（VideoNode/ImageNode/TextNode/AudioNode）按
    categories.{功能分类}.models[modelId] 查找 schema，
    所以需要将组件注入到正确的功能分类中。
    """
    if not output_type:
        return None
    ot = output_type.lower()
    if "video" in ot:
        return "video"
    if "image" in ot:
        return "image"
    if "audio" in ot:
        return "audio"
    if "text" in ot:
        return "text"
    return None


def _normalize_properties(properties: dict) -> dict:
    """将 JSON Schema 属性标准化为 RenderField.jsx 兼容格式

    RenderField.jsx 使用的字段名与 JSON Schema 标准不同：
    - type "integer" → "int"
    - minimum → minValue
    - maximum → maxValue
    """
    for prop in properties.values():
        # 标准化类型名
        if prop.get("type") == "integer":
            prop["type"] = "int"
        elif prop.get("type") == "number":
            prop["type"] = "int"
        # 标准化范围字段名
        if "minimum" in prop and "minValue" not in prop:
            prop["minValue"] = prop.pop("minimum")
        if "maximum" in prop and "maxValue" not in prop:
            prop["maxValue"] = prop.pop("maximum")
    return properties


def component_to_node_schema(component: Component) -> dict:
    """将 Component 转换为 workflow node-schemas 格式

    返回的字典结构对应 /api/workflow/{id}/node-schemas 中
    categories.{category}.models.{model_id} 的格式
    """
    meta = component.meta

    # 构建 input_schema（前端表单结构），先标准化属性名以兼容 RenderField.jsx
    input_properties = _normalize_properties(dict(meta.input_schema))
    input_schema = {
        "schemas": {
            "input_data": {
                "properties": input_properties,
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

    组件会同时注入到两个位置：
    1. 功能分类（video/image/audio/text）— 供节点组件查找 schema 和输入端口
    2. custom 分类 — 供前端 NodesNavbar 展示"自定义组件"入口

    Args:
        base_schemas: 从 _base_schemas() 或 get_node_schemas() 获取的 schemas 字典

    Returns:
        注入后的 schemas（直接修改传入的字典）
    """
    from .registry import ComponentRegistry

    # 确保 categories 存在
    if "categories" not in base_schemas:
        base_schemas["categories"] = {}

    for comp_id, comp in ComponentRegistry.list_components().items():
        meta = comp.meta
        node_schema = comp.to_node_schema()
        node_schema["subcategory"] = meta.subcategory

        # 1) 保留在 custom 分类（供前端 NodesNavbar 发现"自定义组件"）
        custom_key = "custom"
        if custom_key not in base_schemas["categories"]:
            base_schemas["categories"][custom_key] = {
                "name": "Custom Components",
                "models": {},
            }
        base_schemas["categories"][custom_key]["models"][comp_id] = node_schema

        # 2) 注入到功能分类（供节点组件 VideoNode/ImageNode/TextNode/AudioNode 查找 schema）
        func_cat = _output_type_to_functional_category(meta.output_type)
        if func_cat and func_cat != custom_key:
            if func_cat in base_schemas["categories"]:
                base_schemas["categories"][func_cat]["models"][comp_id] = node_schema

    return base_schemas
