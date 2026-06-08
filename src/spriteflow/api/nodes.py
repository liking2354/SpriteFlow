"""节点 API — 列出可用节点 + schema"""

from __future__ import annotations

from fastapi import APIRouter

from ..engine.node import get_node_registry

router = APIRouter()

_NODE_UI: dict[str, dict] = {
    "CharacterMaster": {
        "label": "角色母版",
        "icon": "👤",
        "color": "#3b82f6",
        "description": "根据模板拼装 prompt 生成角色基础形象",
        "params": {
            "template_ids": {"label": "模板ID", "widget": "select", "options_source": "templates", "multiple": True, "help": "选择规格书+角色模板，按类型优先级自动排序拼装"},
            "slot_values": {"label": "Slot值", "widget": "json", "placeholder": '{"character_desc": "dark warrior", "color_palette": "crimson, gold"}'},
            "style_prompt": {"label": "风格提示词", "widget": "textarea", "placeholder": "pixel art, dark armor, red cape..."},
            "size": {"label": "尺寸", "widget": "size"},
            "canvas_width": {"label": "画布宽度", "widget": "number"},
            "canvas_height": {"label": "画布高度", "widget": "number"},
            "target_width": {"label": "角色宽度", "widget": "number"},
            "target_height": {"label": "角色高度", "widget": "number"},
            "detect_threshold": {"label": "检测阈值", "widget": "number"},
            "padding": {"label": "边距", "widget": "number"},
            "seed": {"label": "随机种子", "widget": "number"},
            "watermark": {"label": "水印", "widget": "select"},
            "output_format": {"label": "输出格式", "widget": "text"},
        },
    },
    "DirectionVariant": {
        "label": "方向变体",
        "icon": "🧭",
        "color": "#10b981",
        "description": "基于上游素材 + 方向/职业模板生成角色变体（合并旧 FourDirection + ClassDerive）",
        "params": {
            "template_ids": {"label": "模板ID", "widget": "select", "options_source": "templates", "multiple": True, "help": "选择方向或职业模板"},
            "slot_values": {"label": "Slot值", "widget": "json", "placeholder": '{"action_frames": "4"}'},
            "size": {"label": "尺寸", "widget": "size"},
            "seed": {"label": "随机种子", "widget": "number"},
            "watermark": {"label": "水印", "widget": "select"},
            "output_format": {"label": "输出格式", "widget": "text"},
        },
    },
    "AnimationSprite": {
        "label": "动画精灵",
        "icon": "🏃",
        "color": "#f59e0b",
        "description": "基于上游素材 + 动作模板生成动画序列帧（合并旧 ActionDerive + EquipmentDerive）",
        "params": {
            "template_ids": {"label": "模板ID", "widget": "select", "options_source": "templates", "multiple": True, "help": "选择动作模板"},
            "slot_values": {"label": "Slot值", "widget": "json", "placeholder": '{"action_desc": "sword slash", "frames_spec": "8"}'},
            "max_images": {"label": "最大帧数", "widget": "number"},
            "size": {"label": "尺寸", "widget": "size"},
            "seed": {"label": "随机种子", "widget": "number"},
            "watermark": {"label": "水印", "widget": "select"},
            "output_format": {"label": "输出格式", "widget": "text"},
        },
    },
    "SkillVFX": {
        "label": "技能特效",
        "icon": "💥",
        "color": "#6366f1",
        "description": "根据 VFX 模板生成技能特效序列帧",
        "params": {
            "template_ids": {"label": "模板ID", "widget": "select", "options_source": "templates", "multiple": True, "help": "选择 VFX 模板"},
            "slot_values": {"label": "Slot值", "widget": "json", "placeholder": '{"vfx_name": "fireball", "vfx_type": "projectile", "frames": "8"}'},
            "max_images": {"label": "最大帧数", "widget": "number"},
            "size": {"label": "尺寸", "widget": "size"},
            "seed": {"label": "随机种子", "widget": "number"},
            "watermark": {"label": "水印", "widget": "select"},
            "output_format": {"label": "输出格式", "widget": "text"},
        },
    },
    "ImageFusion": {
        "label": "图像融合",
        "icon": "🎨",
        "color": "#ec4899",
        "description": "融合多张素材图为一张完整图（管线包装 MultiImageFusion）",
        "params": {
            "template_ids": {"label": "模板ID", "widget": "select", "options_source": "templates", "multiple": True, "help": "可选融合模板"},
            "slot_values": {"label": "Slot值", "widget": "json", "placeholder": "{}"},
            "size": {"label": "尺寸", "widget": "size"},
            "seed": {"label": "随机种子", "widget": "number"},
            "watermark": {"label": "水印", "widget": "select"},
            "output_format": {"label": "输出格式", "widget": "text"},
        },
    },
    "ImageViewer": {
        "label": "图片查看",
        "icon": "🖼️",
        "color": "#22c55e",
        "description": "展示上游单张生成结果图片",
        "params": {},
    },
    "GalleryViewer": {
        "label": "图库查看",
        "icon": "🖼️",
        "color": "#22c55e",
        "description": "展示上游批量生成结果（序列帧）",
        "params": {},
    },
}


def _param_schema(node_type: str, param) -> dict:
    ui = _NODE_UI.get(node_type, {}).get("params", {}).get(param.name, {})
    choices = ui.get("choices", param.choices)
    return {
        "name": param.name,
        "type": param.param_type,
        "label": ui.get("label", param.name),
        "widget": ui.get("widget") or ("select" if choices else "number" if param.param_type in {"int", "float", "seed"} else "text"),
        "default": param.default,
        "required": param.required,
        "min": param.min_val,
        "max": param.max_val,
        "choices": choices,
        "placeholder": ui.get("placeholder"),
        "help": ui.get("help"),
        "options_source": ui.get("options_source"),
        "multiple": bool(ui.get("multiple", False)),
    }


@router.get("/nodes")
async def list_nodes(category: str | None = None):
    """列出所有可用节点及其 schema"""
    registry = get_node_registry()
    result = []
    for name, cls in registry.items():
        instance = cls()
        if category and instance.CATEGORY != category:
            continue
        ui = _NODE_UI.get(name, {})
        result.append({
            "type": name,
            "label": ui.get("label", name),
            "icon": ui.get("icon", "📦"),
            "color": ui.get("color", "#6366f1"),
            "description": ui.get("description", ""),
            "category": instance.CATEGORY,
            "inputs": {k: v.value for k, v in instance.INPUTS.items()},
            "outputs": {k: v.value for k, v in instance.OUTPUTS.items()},
            "params": [_param_schema(name, p) for p in instance.PARAMS],
        })
    return result
