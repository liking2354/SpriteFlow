"""
模型注册表 — 模型 ID 到服务的映射 + 本地 Schema 生成

提供与 MuAPI 兼容的 categories Schema JSON
"""
import logging
from typing import Optional
from .base import AIServiceBase
from .openai_service import OpenAICompatibleService
from .replicate_service import ReplicateService
from .ollama_service import OllamaService

logger = logging.getLogger(__name__)

# ===========================================================================
# 服务实例（懒加载）
# ===========================================================================
_services: dict[str, AIServiceBase] = {}

# 自定义模型注册表（从 DB 同步到内存）
_custom_registry: dict[str, str] = {}          # model_id → service_name
_custom_node_schemas: dict[str, dict] = {}     # category → {model_id: node_def}


def _get_or_create(cls, name: str) -> AIServiceBase:
    if name not in _services:
        _services[name] = cls()
    return _services[name]


def register_custom_model(model_id: str, service_name: str, category: str, node_def: dict, subcategory: str = ""):
    """注册一个自定义模型到内存注册表"""
    _custom_registry[model_id.lower()] = service_name
    _custom_node_schemas.setdefault(category, {})[model_id] = node_def
    _custom_node_schemas.setdefault(category, {})[model_id]["subcategory"] = subcategory


def unregister_custom_model(model_id: str):
    """从内存注册表移除一个自定义模型"""
    _custom_registry.pop(model_id.lower(), None)
    for cat_models in _custom_node_schemas.values():
        cat_models.pop(model_id, None)


def _derive_subcategory(model_id: str) -> str:
    """根据模型 ID 推导子分类（与前端 NodesNavbar 分类逻辑一致）"""
    lower = model_id.lower()
    if "edit" in lower or "reference" in lower or "image-to-image" in lower:
        return "editing"
    return "generation"


async def seed_builtin_models_to_db(db):
    """启动时将内置 AI 模型写入 CustomNodeSchema 表（已有则不覆盖），统一存储"""
    from sqlalchemy import select as sa_select
    from ..models import CustomNodeSchema, ModelConfig

    full_schemas = _full_node_schemas()
    count = 0
    skipped = 0

    # 查询所有已软删除的模型 ID
    deleted_result = await db.execute(
        sa_select(ModelConfig.model_id).where(ModelConfig.is_deleted == "true")
    )
    deleted_ids = set(row[0] for row in deleted_result.fetchall())

    for cat_key, cat_data in full_schemas.get("categories", {}).items():
        if cat_key in ("utility",):
            continue
        for model_id, node_def in cat_data.get("models", {}).items():
            service = MODEL_REGISTRY.get(model_id, "")
            if service == "passthrough":
                continue

            # 跳过用户已软删除的模型
            if model_id in deleted_ids:
                skipped += 1
                continue

            # 推导子分类（仅 image/video 需要）
            subcategory = _derive_subcategory(model_id) if cat_key in ("image", "video") else ""

            # 检查是否已存在 — 已存在的合并更新 input_schema（新增属性不覆盖已有）
            existing = (await db.execute(
                sa_select(CustomNodeSchema).where(CustomNodeSchema.model_id == model_id)
            )).scalar_one_or_none()
            if existing is not None:
                # 合并新属性到已有 schema 中（保留用户自定义字段）
                new_input = node_def.get("input_schema", {})
                new_props = new_input.get("schemas", {}).get("input_data", {}).get("properties", {})
                existing_input = existing.input_schema or {}
                existing_props = existing_input.get("schemas", {}).get("input_data", {}).get("properties", {})
                if new_props:
                    merged_props = {**new_props, **existing_props}  # 已存在的属性优先
                    if "schemas" not in existing_input:
                        existing_input = {"schemas": {"input_data": {"properties": {}, "required": []}}}
                    existing_input["schemas"]["input_data"]["properties"] = merged_props
                    # 合并 required 列表
                    new_required = new_input.get("schemas", {}).get("input_data", {}).get("required", [])
                    existing_required = existing_input["schemas"]["input_data"].get("required", [])
                    merged_required = list(dict.fromkeys([*existing_required, *new_required]))
                    existing_input["schemas"]["input_data"]["required"] = merged_required
                    existing.input_schema = existing_input
                    logger.info(f"[seed_builtin_models] 已更新模型 {model_id} 的 input_schema")
                # 补全子分类
                if not existing.subcategory and subcategory:
                    existing.subcategory = subcategory
                skipped += 1
                continue

            db.add(CustomNodeSchema(
                model_id=model_id,
                category=cat_key,
                subcategory=subcategory,
                name=node_def.get("name", model_id),
                service=service,
                input_schema=node_def.get("input_schema", {}),
            ))
            count += 1

    if count or skipped:
        await db.flush()
        logger.info(f"[seed_builtin_models] 新增 {count} 个，跳过 {skipped} 个已有模型")

    # 为所有已有模型补充标准分类属性（image/video 的 images_list, image_url 等）
    category_props = {
        "text": _TEXT_PROPS,
        "image": _IMG_PROPS,
        "video": _VID_PROPS,
    }
    updated_count = 0
    from sqlalchemy import update as sa_update
    all_rows = (await db.execute(
        sa_select(CustomNodeSchema.id, CustomNodeSchema.model_id, CustomNodeSchema.category, CustomNodeSchema.input_schema)
    )).all()
    for row_id, model_id, category, input_schema in all_rows:
        if category not in category_props:
            continue
        if model_id in deleted_ids:
            continue
        std_props = category_props[category]
        existing_input = input_schema or {}
        if "schemas" not in existing_input:
            existing_input = {"schemas": {"input_data": {"properties": {}, "required": []}}}
        existing_props = existing_input.get("schemas", {}).get("input_data", {}).get("properties", {})
        merged = {**std_props, **existing_props}
        if set(merged.keys()) != set(existing_props.keys()):
            existing_input["schemas"]["input_data"]["properties"] = merged
            await db.execute(
                sa_update(CustomNodeSchema)
                .where(CustomNodeSchema.id == row_id)
                .values(input_schema=existing_input)
            )
            updated_count += 1
    if updated_count:
        await db.flush()
        logger.info(f"[seed_builtin_models] 已为 {updated_count} 个已有模型补充分类属性")


async def sync_custom_nodes_to_registry(db):
    """启动时从 DB 同步所有模型节点到内存注册表"""
    from sqlalchemy import select
    from ..models import CustomNodeSchema

    _custom_registry.clear()
    _custom_node_schemas.clear()

    result = await db.execute(select(CustomNodeSchema))
    for row in result.scalars().all():
        node_def = {
            "name": row.name,
            "input_schema": row.input_schema or {},
            "subcategory": getattr(row, "subcategory", "") or "",
        }
        register_custom_model(row.model_id, row.service, row.category, node_def, node_def["subcategory"])


# ===========================================================================
# 模型 ID → 服务名 注册表
# ===========================================================================
MODEL_REGISTRY: dict[str, str] = {
    # ===== Passthrough 模型（透传输入，非 AI） =====
    "text-passthrough": "passthrough",
    "image-passthrough": "passthrough",
    "video-passthrough": "passthrough",
    "audio-passthrough": "passthrough",

    # ===== 文本模型 → OpenAI 兼容 =====
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4-turbo": "openai",
    "gpt-5-nano": "openai",
    "gpt-5-mini": "openai",
    "gpt-image-1.5": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4-mini": "openai",
    "claude-sonnet-4-20250514": "openai",
    "claude-3-5-sonnet-20241022": "openai",
    "claude-3-5-haiku-20241022": "openai",
    "claude-3-opus-20240229": "openai",
    "claude-3-haiku-20240307": "openai",
    "gemini-2.5-flash": "openai",
    "gemini-2.5-pro": "openai",
    "gemini-2.0-flash": "openai",
    "deepseek-r1": "openai",
    "deepseek-v3": "openai",
    "deepseek-chat": "openai",
    "llama-4-maverick": "ollama",
    "llama-4-scout": "ollama",
    "any-llm": "openai",
    "openrouter-vision": "openai",

    # ===== 图像模型 → Replicate =====
    "flux-schnell": "replicate",
    "flux-2-dev": "replicate",
    "flux-2-flex": "replicate",
    "flux-2-pro": "replicate",
    "flux-1.1-pro": "replicate",
    "flux-1.1-pro-ultra": "replicate",
    "flux-pro": "replicate",
    "flux-dev": "replicate",
    "flux-2-dev-edit": "replicate",
    "flux-2-flex-edit": "replicate",
    "flux-2-pro-edit": "replicate",
    "sd-turbo-ultra": "replicate",
    "sd-core-ultra": "replicate",
    "wan2.5-text-to-image": "replicate",
    "wan2.5-image-edit": "replicate",
    "wan2.6-text-to-image": "replicate",

    # ===== 视频模型 → Replicate =====
    "wan-2.1": "replicate",
    "wan-2.2": "replicate",
    "wan2.5-image-to-video": "replicate",
    "wan2.5-text-to-video": "replicate",
    "wan2.5-image-to-video-fast": "replicate",
    "wan2.5-text-to-video-fast": "replicate",
    "wan2.6-image-to-video": "replicate",
    "wan2.6-text-to-video": "replicate",
    "wan2.2-text-to-video": "replicate",
    "wan2.2-image-to-video": "replicate",
    "wan2.2-5b-fast-t2v": "replicate",
    "wan2.2-animate": "replicate",
    "wan2.2-edit-video": "replicate",
    "wan2.2-spicy-image-to-video": "replicate",
    "wan2.2-spicy-video-extend": "replicate",

    # ===== 直连模型 =====
    "bytedance-seedream-v4": "replicate",
    "bytedance-seedream-v4.5": "replicate",
    "bytedance-seedream-edit-v4": "replicate",
    "bytedance-seedream-v4.5-edit": "replicate",
    "seedance-lite-i2v": "replicate",
    "seedance-lite-t2v": "replicate",
    "seedance-pro-t2v": "replicate",
    "seedance-pro-i2v": "replicate",
    "seedance-pro-t2v-fast": "replicate",
    "seedance-pro-i2v-fast": "replicate",
    "seedance-v1.5-pro-i2v": "replicate",
    "seedance-v1.5-pro-t2v": "replicate",
    "seedance-v1.5-pro-i2v-fast": "replicate",
    "seedance-v1.5-pro-t2v-fast": "replicate",
    "seedance-v1.5-pro-video-extend": "replicate",
    "seedance-v1.5-pro-video-extend-fast": "replicate",

    # ===== 额外图像模型 → Replicate =====
    "nano-banana": "replicate",
    "nano-banana-edit": "replicate",
    "nano-banana-pro": "replicate",
    "nano-banana-pro-edit": "replicate",
    "qwen-image": "replicate",
    "qwen-image-edit-2511": "replicate",
    "qwen-image-edit": "replicate",
    "qwen-image-edit-plus": "replicate",
    "qwen-image-edit-plus-lora": "replicate",
    "z-image-turbo": "replicate",
    "chroma-image": "replicate",
    "kling-o1-text-to-image": "replicate",
    "kling-o1-edit-image": "replicate",
    "grok-imagine-text-to-image": "replicate",
    "hunyuan-image-2.1": "replicate",
    "hunyuan-image-3.0": "replicate",
    "google-imagen4": "replicate",
    "google-imagen4-fast": "replicate",
    "google-imagen4-ultra": "replicate",
    "midjourney-v7-text-to-image": "replicate",
    "midjourney-v7-image-to-image": "replicate",
    "midjourney-v7-omni-reference": "replicate",
    "midjourney-v7-style-reference": "replicate",
    "vidu-q2-text-to-image": "replicate",
    "vidu-q2-reference-to-image": "replicate",
    "wan2.6-image-edit": "replicate",

    # ===== 额外视频模型 → Replicate =====
    "midjourney-v7-image-to-video": "replicate",
    "openai-sora": "replicate",
    "openai-sora-2-text-to-video": "replicate",
    "openai-sora-2-image-to-video": "replicate",
    "openai-sora-2-pro-text-to-video": "replicate",
    "openai-sora-2-pro-image-to-video": "replicate",
    "kling-v2.5-turbo-pro-t2v": "replicate",
    "kling-v2.5-turbo-pro-i2v": "replicate",
    "kling-v2.5-turbo-std-i2v": "replicate",
    "kling-v2.6-pro-t2v": "replicate",
    "kling-v2.6-pro-i2v": "replicate",
    "kling-v2.6-pro-motion-control": "replicate",
    "kling-o1-text-to-video": "replicate",
    "kling-o1-image-to-video": "replicate",
    "kling-o1-video-edit": "replicate",
    "kling-o1-video-edit-fast": "replicate",
    "kling-o1-reference-to-video": "replicate",
    "kling-o1-standard-image-to-video": "replicate",
    "kling-o1-standard-reference-to-video": "replicate",
    "kling-o1-standard-video-edit": "replicate",
    "grok-imagine-text-to-video": "replicate",
    "grok-imagine-image-to-video": "replicate",
    "hunyuan-text-to-video": "replicate",
    "hunyuan-fast-text-to-video": "replicate",
    "hunyuan-image-to-video": "replicate",
    "vidu-q2-turbo-start-end-video": "replicate",
    "vidu-q2-pro-start-end-video": "replicate",
    "vidu-q2-reference": "replicate",
    "luma-modify-video": "replicate",
    "luma-flash-reframe": "replicate",
    "veo3.1-image-to-video": "replicate",
    "veo3.1-text-to-video": "replicate",
    "veo3.1-fast-image-to-video": "replicate",
    "veo3.1-fast-text-to-video": "replicate",

    # ===== 音频模型 → OpenAI(tts) 或 Ollama =====
    "openai-tts": "openai",
    "suno-create-music": "openai",
    "suno-extend-music": "openai",
    "suno-remix-music": "openai",
    "minimax-voice-clone": "openai",
    "minimax-speech-2.6-hd": "openai",
    "minimax-speech-2.6-turbo": "openai",
}


def get_service(model_id: str) -> Optional[AIServiceBase]:
    """
    根据模型 ID 获取对应的 AI 服务实例

    Args:
        model_id: 模型标识符，如 "gpt-4o", "flux-dev"

    Returns:
        AIServiceBase 实例或 None（不支持此模型）
    """
    key = model_id.lower()
    service_name = MODEL_REGISTRY.get(key)
    if not service_name:
        service_name = _custom_registry.get(key)
    if not service_name:
        return None

    if service_name == "openai":
        return _get_or_create(OpenAICompatibleService, "openai")
    elif service_name == "replicate":
        return _get_or_create(ReplicateService, "replicate")
    elif service_name == "ollama":
        return _get_or_create(OllamaService, "ollama")

    return None


# ===========================================================================
# 本地 Schema 生成 — 完全替代 MuAPI 的 node-schemas 返回
# ===========================================================================

def _build_input_schema(properties: dict, required: list[str] = None) -> dict:
    """构建标准 input_schema 结构"""
    return {
        "schemas": {
            "input_data": {
                "properties": properties,
                "required": required or list(properties.keys()),
            }
        }
    }


_TEXT_PROPS = {
    "prompt": {"type": "string", "title": "Prompt", "description": "The text prompt"},
    "system_prompt": {"type": "string", "title": "System Prompt", "description": "System instructions"},
    "image_url": {"type": "string", "title": "Image URL", "description": "Input image URL (vision)"},
    "temperature": {"type": "number", "title": "Temperature", "default": 0.7, "minimum": 0, "maximum": 2},
    "max_tokens": {"type": "integer", "title": "Max Tokens", "default": 4096},
}

_IMG_PROPS = {
    "prompt": {"type": "string", "title": "Prompt", "description": "Text prompt for image generation"},
    "image_url": {"type": "string", "title": "Image URL", "description": "Input image URL"},
    "images_list": {"type": "array", "title": "Images List", "description": "Input images list"},
    "width": {"type": "integer", "title": "Width", "default": 1024},
    "height": {"type": "integer", "title": "Height", "default": 1024},
    "num_outputs": {"type": "integer", "title": "Count", "default": 1},
    "seed": {"type": "integer", "title": "Seed"},
    "negative_prompt": {"type": "string", "title": "Negative Prompt"},
}

_VID_PROPS = {
    "prompt": {"type": "string", "title": "Prompt", "description": "Text prompt for video generation"},
    "image_url": {"type": "string", "title": "Input Image URL", "description": "Source image for I2V"},
    "last_image": {"type": "string", "title": "Last Frame Image", "description": "Last frame image for video-to-video"},
    "video_url": {"type": "string", "title": "Input Video URL", "description": "Source video URL"},
    "audio_url": {"type": "string", "title": "Input Audio URL", "description": "Source audio URL"},
    "images_list": {"type": "array", "title": "Images List", "description": "Input images list"},
    "videos_list": {"type": "array", "title": "Videos List", "description": "Input videos list"},
    "video_files": {"type": "array", "title": "Video Files", "description": "Input video files"},
    "audios_list": {"type": "array", "title": "Audios List", "description": "Input audios list"},
    "audio_files": {"type": "array", "title": "Audio Files", "description": "Input audio files"},
    "duration": {"type": "integer", "title": "Duration (s)", "default": 5},
    "fps": {"type": "integer", "title": "FPS", "default": 16},
}

# ===== 模型定义辅助 =====
def _m(name, props, required):
    return {"name": name, "input_schema": _build_input_schema(props, required)}


def _full_node_schemas() -> dict:
    """
    返回所有内置模型的 Schema（含 AI 模型 + passthrough + utility）
    由 seed_builtin_models_to_db() 读取，将 AI 模型写入数据库统一存储
    """
    t = _TEXT_PROPS
    i = _IMG_PROPS
    v = _VID_PROPS

    _pin = {"prompt": {"type": "string", "title": "Prompt"}}
    _audio_txt = {"prompt": {"type": "string", "title": "Prompt", "description": "Text to generate audio from"}}

    return {
        "categories": {
            "text": {"name": "Text Models", "models": {
                "text-passthrough": _m("Input Text", _pin, ["prompt"]),
                "gpt-4o": _m("GPT-4o", t, ["prompt"]),
                "gpt-4o-mini": _m("GPT-4o Mini", t, ["prompt"]),
                "gpt-4-turbo": _m("GPT-4 Turbo", t, ["prompt"]),
                "gpt-5-nano": _m("GPT-5 Nano", t, ["prompt"]),
                "gpt-5-mini": _m("GPT-5 Mini", t, ["prompt"]),
                "gpt-image-1.5": _m("GPT Image 1.5", t, ["prompt"]),
                "o1": _m("o1", t, ["prompt"]),
                "o3": _m("o3", t, ["prompt"]),
                "o4-mini": _m("o4-mini", t, ["prompt"]),
                "claude-sonnet-4-20250514": _m("Claude Sonnet 4", t, ["prompt"]),
                "claude-3-5-sonnet-20241022": _m("Claude 3.5 Sonnet", t, ["prompt"]),
                "claude-3-5-haiku-20241022": _m("Claude 3.5 Haiku", t, ["prompt"]),
                "claude-3-opus-20240229": _m("Claude 3 Opus", t, ["prompt"]),
                "claude-3-haiku-20240307": _m("Claude 3 Haiku", t, ["prompt"]),
                "deepseek-r1": _m("DeepSeek R1", t, ["prompt"]),
                "deepseek-v3": _m("DeepSeek V3", t, ["prompt"]),
                "deepseek-chat": _m("DeepSeek Chat", t, ["prompt"]),
                "gemini-2.5-flash": _m("Gemini 2.5 Flash", t, ["prompt"]),
                "gemini-2.5-pro": _m("Gemini 2.5 Pro", t, ["prompt"]),
                "gemini-2.0-flash": _m("Gemini 2.0 Flash", t, ["prompt"]),
                "llama-4-maverick": _m("Llama 4 Maverick", t, ["prompt"]),
                "llama-4-scout": _m("Llama 4 Scout", t, ["prompt"]),
                "any-llm": _m("Any LLM", t, ["prompt"]),
                "openrouter-vision": _m("OpenRouter Vision", t, ["prompt"]),
            }},
            "image": {"name": "Image Models", "models": {
                "image-passthrough": _m("Input Image",
                    {"image_url": {"type": "string", "title": "Image URL"}}, ["image_url"]),
                "gpt-image-1.5": _m("GPT Image 1.5", i, ["prompt"]),
                "nano-banana": _m("Nano Banana", i, ["prompt"]),
                "nano-banana-edit": _m("Nano Banana Edit", i, ["prompt"]),
                "nano-banana-pro": _m("Nano Banana Pro", i, ["prompt"]),
                "nano-banana-pro-edit": _m("Nano Banana Pro Edit", i, ["prompt"]),
                "flux-schnell": _m("Flux Schnell", i, ["prompt"]),
                "flux-2-dev": _m("Flux 2 Dev", i, ["prompt"]),
                "flux-2-dev-edit": _m("Flux 2 Dev Edit", i, ["prompt"]),
                "flux-2-flex": _m("Flux 2 Flex", i, ["prompt"]),
                "flux-2-flex-edit": _m("Flux 2 Flex Edit", i, ["prompt"]),
                "flux-2-pro": _m("Flux 2 Pro", i, ["prompt"]),
                "flux-2-pro-edit": _m("Flux 2 Pro Edit", i, ["prompt"]),
                "flux-1.1-pro": _m("Flux 1.1 Pro", i, ["prompt"]),
                "flux-1.1-pro-ultra": _m("Flux 1.1 Pro Ultra", i, ["prompt"]),
                "bytedance-seedream-v4": _m("Seedream v4", i, ["prompt"]),
                "bytedance-seedream-v4.5": _m("Seedream v4.5", i, ["prompt"]),
                "wan2.5-text-to-image": _m("Wan 2.5 T2I", i, ["prompt"]),
                "wan2.5-image-edit": _m("Wan 2.5 Image Edit", i, ["prompt"]),
                "wan2.6-text-to-image": _m("Wan 2.6 T2I", i, ["prompt"]),
                "qwen-image": _m("Qwen Image", i, ["prompt"]),
                "qwen-image-edit-2511": _m("Qwen Image Edit 2511", i, ["prompt"]),
                "qwen-image-edit": _m("Qwen Image Edit", i, ["prompt"]),
                "qwen-image-edit-plus": _m("Qwen Image Edit Plus", i, ["prompt"]),
                "qwen-image-edit-plus-lora": _m("Qwen Image Edit Plus LoRA", i, ["prompt"]),
                "z-image-turbo": _m("Z Image Turbo", i, ["prompt"]),
                "chroma-image": _m("Chroma Image", i, ["prompt"]),
                "kling-o1-text-to-image": _m("Kling O1 T2I", i, ["prompt"]),
                "kling-o1-edit-image": _m("Kling O1 Edit Image", i, ["prompt"]),
                "grok-imagine-text-to-image": _m("Grok Imagine", i, ["prompt"]),
                "hunyuan-image-2.1": _m("Hunyuan Image 2.1", i, ["prompt"]),
                "hunyuan-image-3.0": _m("Hunyuan Image 3.0", i, ["prompt"]),
                "google-imagen4": _m("Google Imagen 4", i, ["prompt"]),
                "google-imagen4-fast": _m("Google Imagen 4 Fast", i, ["prompt"]),
                "google-imagen4-ultra": _m("Google Imagen 4 Ultra", i, ["prompt"]),
                "midjourney-v7-text-to-image": _m("Midjourney v7 T2I", i, ["prompt"]),
                "midjourney-v7-image-to-image": _m("Midjourney v7 I2I", i, ["prompt"]),
                "midjourney-v7-omni-reference": _m("Midjourney v7 Omni Ref", i, ["prompt"]),
                "midjourney-v7-style-reference": _m("Midjourney v7 Style Ref", i, ["prompt"]),
                "vidu-q2-text-to-image": _m("Vidu Q2 T2I", i, ["prompt"]),
                "vidu-q2-reference-to-image": _m("Vidu Q2 Reference", i, ["prompt"]),
                "sd-turbo-ultra": _m("SD Turbo Ultra", i, ["prompt"]),
                "sd-core-ultra": _m("SD Core Ultra", i, ["prompt"]),
                "wan2.6-image-edit": _m("Wan 2.6 Image Edit", i, ["prompt"]),
                "bytedance-seedream-edit-v4": _m("Seedream Edit v4", i, ["prompt"]),
                "bytedance-seedream-v4.5-edit": _m("Seedream v4.5 Edit", i, ["prompt"]),
            }},
            "video": {"name": "Video Models", "models": {
                "video-passthrough": _m("Input Video",
                    {"video_url": {"type": "string", "title": "Video URL"}}, ["video_url"]),
                "seedance-lite-i2v": _m("Seedance Lite I2V", v, ["prompt", "image_url"]),
                "seedance-lite-t2v": _m("Seedance Lite T2V", v, ["prompt"]),
                "seedance-pro-t2v": _m("Seedance Pro T2V", v, ["prompt"]),
                "seedance-pro-i2v": _m("Seedance Pro I2V", v, ["prompt", "image_url"]),
                "seedance-pro-t2v-fast": _m("Seedance Pro T2V Fast", v, ["prompt"]),
                "seedance-pro-i2v-fast": _m("Seedance Pro I2V Fast", v, ["prompt", "image_url"]),
                "seedance-v1.5-pro-i2v": _m("Seedance v1.5 Pro I2V", v, ["prompt", "image_url"]),
                "seedance-v1.5-pro-t2v": _m("Seedance v1.5 Pro T2V", v, ["prompt"]),
                "seedance-v1.5-pro-i2v-fast": _m("Seedance v1.5 Pro I2V Fast", v, ["prompt", "image_url"]),
                "seedance-v1.5-pro-t2v-fast": _m("Seedance v1.5 Pro T2V Fast", v, ["prompt"]),
                "seedance-v1.5-pro-video-extend": _m("Seedance v1.5 Pro Extend", v, ["prompt", "video_url"]),
                "seedance-v1.5-pro-video-extend-fast": _m("Seedance v1.5 Pro Extend Fast", v, ["prompt", "video_url"]),
                "veo3.1-image-to-video": _m("Veo3.1 I2V", v, ["prompt", "image_url"]),
                "veo3.1-text-to-video": _m("Veo3.1 T2V", v, ["prompt"]),
                "veo3.1-fast-image-to-video": _m("Veo3.1 Fast I2V", v, ["prompt", "image_url"]),
                "veo3.1-fast-text-to-video": _m("Veo3.1 Fast T2V", v, ["prompt"]),
                "wan-2.1": _m("Wan 2.1 I2V", v, ["prompt", "image_url"]),
                "wan-2.2": _m("Wan 2.2 I2V", v, ["prompt", "image_url"]),
                "wan2.2-text-to-video": _m("Wan 2.2 T2V", v, ["prompt"]),
                "wan2.2-image-to-video": _m("Wan 2.2 I2V", v, ["prompt", "image_url"]),
                "wan2.2-5b-fast-t2v": _m("Wan 2.2 5B Fast T2V", v, ["prompt"]),
                "wan2.2-animate": _m("Wan 2.2 Animate", v, ["prompt", "image_url"]),
                "wan2.2-edit-video": _m("Wan 2.2 Edit Video", v, ["prompt", "video_url"]),
                "wan2.2-spicy-image-to-video": _m("Wan 2.2 Spicy I2V", v, ["prompt", "image_url"]),
                "wan2.2-spicy-video-extend": _m("Wan 2.2 Spicy Extend", v, ["prompt", "video_url"]),
                "wan2.5-text-to-video": _m("Wan 2.5 T2V", v, ["prompt"]),
                "wan2.5-image-to-video": _m("Wan 2.5 I2V", v, ["prompt", "image_url"]),
                "wan2.5-text-to-video-fast": _m("Wan 2.5 Fast T2V", v, ["prompt"]),
                "wan2.5-image-to-video-fast": _m("Wan 2.5 Fast I2V", v, ["prompt", "image_url"]),
                "wan2.6-text-to-video": _m("Wan 2.6 T2V", v, ["prompt"]),
                "wan2.6-image-to-video": _m("Wan 2.6 I2V", v, ["prompt", "image_url"]),
                "openai-sora": _m("OpenAI Sora", v, ["prompt"]),
                "openai-sora-2-text-to-video": _m("Sora 2 T2V", v, ["prompt"]),
                "openai-sora-2-image-to-video": _m("Sora 2 I2V", v, ["prompt", "image_url"]),
                "openai-sora-2-pro-text-to-video": _m("Sora 2 Pro T2V", v, ["prompt"]),
                "openai-sora-2-pro-image-to-video": _m("Sora 2 Pro I2V", v, ["prompt", "image_url"]),
                "kling-v2.5-turbo-pro-t2v": _m("Kling v2.5 Turbo Pro T2V", v, ["prompt"]),
                "kling-v2.5-turbo-pro-i2v": _m("Kling v2.5 Turbo Pro I2V", v, ["prompt", "image_url"]),
                "kling-v2.5-turbo-std-i2v": _m("Kling v2.5 Turbo Std I2V", v, ["prompt", "image_url"]),
                "kling-v2.6-pro-t2v": _m("Kling v2.6 Pro T2V", v, ["prompt"]),
                "kling-v2.6-pro-i2v": _m("Kling v2.6 Pro I2V", v, ["prompt", "image_url"]),
                "kling-v2.6-pro-motion-control": _m("Kling v2.6 Motion Ctrl", v, ["prompt", "image_url"]),
                "kling-o1-text-to-video": _m("Kling O1 T2V", v, ["prompt"]),
                "kling-o1-image-to-video": _m("Kling O1 I2V", v, ["prompt", "image_url"]),
                "kling-o1-video-edit": _m("Kling O1 Video Edit", v, ["prompt", "video_url"]),
                "kling-o1-video-edit-fast": _m("Kling O1 Video Edit Fast", v, ["prompt", "video_url"]),
                "kling-o1-reference-to-video": _m("Kling O1 Ref To Video", v, ["prompt", "image_url"]),
                "kling-o1-standard-image-to-video": _m("Kling O1 Std I2V", v, ["prompt", "image_url"]),
                "kling-o1-standard-reference-to-video": _m("Kling O1 Std Ref", v, ["prompt", "image_url"]),
                "kling-o1-standard-video-edit": _m("Kling O1 Std Edit", v, ["prompt", "video_url"]),
                "grok-imagine-text-to-video": _m("Grok Imagine T2V", v, ["prompt"]),
                "grok-imagine-image-to-video": _m("Grok Imagine I2V", v, ["prompt", "image_url"]),
                "hunyuan-text-to-video": _m("Hunyuan T2V", v, ["prompt"]),
                "hunyuan-fast-text-to-video": _m("Hunyuan Fast T2V", v, ["prompt"]),
                "hunyuan-image-to-video": _m("Hunyuan I2V", v, ["prompt", "image_url"]),
                "midjourney-v7-image-to-video": _m("Midjourney v7 I2V", v, ["prompt", "image_url"]),
                "vidu-q2-turbo-start-end-video": _m("Vidu Q2 Turbo S/E", v, ["prompt"]),
                "vidu-q2-pro-start-end-video": _m("Vidu Q2 Pro S/E", v, ["prompt"]),
                "vidu-q2-reference": _m("Vidu Q2 Reference", v, ["prompt", "image_url"]),
                "luma-modify-video": _m("Luma Modify Video", v, ["prompt", "video_url"]),
                "luma-flash-reframe": _m("Luma Flash Reframe", v, ["prompt", "video_url"]),
                "video-combiner": _m("Video Combiner",
                    {"videos_list": {"type": "array", "title": "Video Clips",
                                     "items": {"type": "string"}, "maxItems": 20},
                     "aspect_ratio": {"type": "string", "title": "Aspect Ratio",
                                      "enum": ["auto","16:9","9:16","1:1","4:3","3:4","21:9","9:21"],
                                      "default": "auto"}}, ["videos_list"]),
            }},
            "audio": {"name": "Audio Models", "models": {
                "audio-passthrough": _m("Input Audio",
                    {"audio_url": {"type": "string", "title": "Audio URL"}}, ["audio_url"]),
                "openai-tts": _m("OpenAI TTS",
                    {"prompt": {"type": "string", "title": "Text to speak"},
                     "voice": {"type": "string", "title": "Voice",
                               "enum": ["alloy","echo","fable","onyx","nova","shimmer"],
                               "default": "alloy"}}, ["prompt"]),
                "suno-create-music": _m("Suno Create Music", _audio_txt, ["prompt"]),
                "suno-extend-music": _m("Suno Extend Music", _audio_txt, ["prompt"]),
                "suno-remix-music": _m("Suno Remix Music", _audio_txt, ["prompt"]),
                "minimax-voice-clone": _m("Minimax Voice Clone", _audio_txt, ["prompt"]),
                "minimax-speech-2.6-hd": _m("Minimax Speech 2.6 HD", _audio_txt, ["prompt"]),
                "minimax-speech-2.6-turbo": _m("Minimax Speech 2.6 Turbo", _audio_txt, ["prompt"]),
            }},
            "utility": {"name": "Utility", "models": {
                "prompt-concatenator": _m("Prompt Concatenator", _pin, ["prompt"]),
                "video-combiner": _m("Video Combiner",
                    {"videos_list": {"type": "array", "title": "Video Clips",
                                     "items": {"type": "string"}, "maxItems": 20},
                     "aspect_ratio": {"type": "string", "title": "Aspect Ratio",
                                      "enum": ["auto","16:9","9:16","1:1","4:3","3:4","21:9","9:21"],
                                      "default": "auto"}}, ["videos_list"]),
            }},
        }
    }


def _base_schemas() -> dict:
    """
    返回运行时基础 Schema — 仅 passthrough / utility 节点
    AI 模型已统一存储到数据库，通过 _custom_node_schemas 读取
    """
    _pin = {"prompt": {"type": "string", "title": "Prompt"}}
    return {
        "categories": {
            "text": {"name": "Text Models", "models": {
                "text-passthrough": _m("Input Text", _pin, ["prompt"]),
            }},
            "image": {"name": "Image Models", "models": {
                "image-passthrough": _m("Input Image",
                    {"image_url": {"type": "string", "title": "Image URL"}}, ["image_url"]),
            }},
            "video": {"name": "Video Models", "models": {
                "video-passthrough": _m("Input Video",
                    {"video_url": {"type": "string", "title": "Video URL"}}, ["video_url"]),
            }},
            "audio": {"name": "Audio Models", "models": {
                "audio-passthrough": _m("Input Audio",
                    {"audio_url": {"type": "string", "title": "Audio URL"}}, ["audio_url"]),
            }},
            "utility": {"name": "Utility", "models": {
                "prompt-concatenator": _m("Prompt Concatenator", _pin, ["prompt"]),
            }},
        }
    }


def get_node_schemas(workflow_id: str = "", visible_models: set = None) -> dict:
    """
    返回节点模型 Schema，可选按可见性过滤
    - workflow_id: 保留兼容旧接口
    - visible_models: 如果提供，只保留在此 set 中的 model_id（None 时全部显示）
    """
    schema = _base_schemas()

    # 合并内存中的自定义节点到对应分类
    for cat_key, models in _custom_node_schemas.items():
        if cat_key in schema["categories"]:
            for model_id, node_def in models.items():
                schema["categories"][cat_key]["models"][model_id] = node_def

    # 注入自定义组件（Component-based，如 Seedance）
    from spriteflow.components.schema_bridge import inject_component_schemas
    inject_component_schemas(schema)

    if visible_models is not None:
        for cat_key in list(schema["categories"].keys()):
            models = schema["categories"][cat_key]["models"]
            filtered = {k: v for k, v in models.items() if k in visible_models}
            schema["categories"][cat_key]["models"] = filtered

    return schema


def get_api_node_schemas(_workflow_id: str = "") -> dict:
    """
    返回 API 节点模型的 Schema — 与 MuAPI 返回格式一致
    """
    return {
        "categories": {
            "api": {
                "name": "API Connectors",
                "models": {
                    "straico": {
                        "name": "Straico API",
                        "input_schema": _build_input_schema({
                            "model_name": {"type": "string", "title": "Model Name",
                                           "required": True},
                            "model_type": {"type": "string", "title": "Model Type",
                                           "enum": ["chat", "image", "video", "audio"],
                                           "default": "chat", "required": True},
                            "api_key": {"type": "string", "title": "API Key",
                                        "format": "text", "required": True},
                        }, ["model_name", "model_type", "api_key"]),
                    },
                    "runware": {
                        "name": "Runware API",
                        "input_schema": _build_input_schema({
                            "api_key": {"type": "string", "title": "API Key",
                                        "required": True},
                            "task_type": {"type": "string", "title": "Task Type",
                                          "enum": ["imageInference", "textToVideo", "imageToVideo",
                                                   "upscale", "removeBackground"],
                                          "default": "imageInference", "required": True},
                            "model_name": {"type": "string", "title": "Model Name"},
                        }, ["task_type", "api_key"]),
                    },
                    "wavespeed": {
                        "name": "Wavespeed API",
                        "input_schema": _build_input_schema({
                            "model_url": {"type": "string", "title": "Model URL",
                                          "required": True},
                            "api_key": {"type": "string", "title": "API Key",
                                        "required": True},
                        }, ["model_url", "api_key"]),
                    },
                    "genvr": {
                        "name": "GenVR API",
                        "input_schema": _build_input_schema({
                            "uid": {"type": "string", "title": "User ID", "required": True},
                            "api_key": {"type": "string", "title": "API Key", "required": True},
                            "category": {"type": "string", "title": "Category", "required": True},
                            "subcategory": {"type": "string", "title": "Subcategory", "required": True},
                        }, ["uid", "api_key", "category", "subcategory"]),
                    },
                },
            }
        }
    }
