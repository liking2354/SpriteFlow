"""
模型设置服务 — 支持运行时通过 API 修改 AI 提供商配置
读取优先级：数据库 > .env 文件
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import ModelSettings

# 默认配置（从 .env 回退）
from ...config import settings as env_settings

DEFAULT_PROVIDERS = {
    "openai": {
        "api_key": env_settings.openai_api_key,
        "base_url": env_settings.openai_base_url,
    },
    "replicate": {
        "api_key": env_settings.replicate_api_token,
        "base_url": "https://api.replicate.com/v1",
    },
    "ollama": {
        "api_key": "",
        "base_url": env_settings.ollama_host,
    },
}


def mask_key(key: str) -> str:
    """遮蔽 API Key，仅显示后 4 位"""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "****" + key[-4:]


async def init_default_settings(db: AsyncSession):
    """初始化默认配置：如果 DB 中不存在，则从 .env 同步"""
    for provider, defaults in DEFAULT_PROVIDERS.items():
        result = await db.execute(
            select(ModelSettings).where(ModelSettings.provider == provider)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            db_setting = ModelSettings(
                provider=provider,
                api_key=defaults["api_key"],
                base_url=defaults["base_url"],
                is_enabled="true",
            )
            db.add(db_setting)
    await db.flush()


async def get_all_settings(db: AsyncSession) -> dict:
    """获取所有提供商的配置（API Key 遮蔽）"""
    result = await db.execute(select(ModelSettings))
    settings_list = result.scalars().all()

    providers = {}
    for s in settings_list:
        providers[s.provider] = {
            "id": s.id,
            "provider": s.provider,
            "api_key": mask_key(s.api_key),
            "has_key": bool(s.api_key),
            "base_url": s.base_url,
            "is_enabled": s.is_enabled == "true",
        }

    # 补全未初始化的提供商
    for provider, defaults in DEFAULT_PROVIDERS.items():
        if provider not in providers:
            providers[provider] = {
                "id": None,
                "provider": provider,
                "api_key": mask_key(defaults["api_key"]),
                "has_key": bool(defaults["api_key"]),
                "base_url": defaults["base_url"],
                "is_enabled": bool(defaults["api_key"]),
            }

    return {"providers": providers}


async def update_provider_settings(db: AsyncSession, provider: str, data: dict) -> dict:
    """更新指定提供商的配置"""
    result = await db.execute(
        select(ModelSettings).where(ModelSettings.provider == provider)
    )
    setting = result.scalar_one_or_none()

    if setting is None:
        setting = ModelSettings(provider=provider, api_key="", base_url="")
        db.add(setting)

    if "api_key" in data and data["api_key"]:
        setting.api_key = data["api_key"]
    if "base_url" in data:
        setting.base_url = data["base_url"] or ""
    if "is_enabled" in data:
        setting.is_enabled = "true" if data["is_enabled"] else "false"

    await db.flush()
    await db.refresh(setting)

    return {
        "id": setting.id,
        "provider": setting.provider,
        "api_key": mask_key(setting.api_key),
        "has_key": bool(setting.api_key),
        "base_url": setting.base_url,
        "is_enabled": setting.is_enabled == "true",
    }


async def create_provider_settings(db: AsyncSession, data: dict) -> dict:
    """创建新的 AI 提供商"""
    provider = (data.get("provider") or "").strip().lower()
    if not provider:
        raise ValueError("Provider name is required")
    if provider in DEFAULT_PROVIDERS:
        raise ValueError(f"Provider '{provider}' already exists as a default provider. Use update instead.")

    # 检查是否已存在
    result = await db.execute(
        select(ModelSettings).where(ModelSettings.provider == provider)
    )
    if result.scalar_one_or_none():
        raise ValueError(f"Provider '{provider}' already exists")

    setting = ModelSettings(
        provider=provider,
        api_key=data.get("api_key", ""),
        base_url=data.get("base_url", ""),
        is_enabled="true" if data.get("is_enabled", True) else "false",
    )
    db.add(setting)
    await db.flush()
    await db.refresh(setting)

    return {
        "id": setting.id,
        "provider": setting.provider,
        "api_key": mask_key(setting.api_key),
        "has_key": bool(setting.api_key),
        "base_url": setting.base_url,
        "is_enabled": setting.is_enabled == "true",
    }


async def delete_provider_settings(db: AsyncSession, provider: str) -> dict:
    """删除一个 AI 提供商"""
    result = await db.execute(
        select(ModelSettings).where(ModelSettings.provider == provider)
    )
    setting = result.scalar_one_or_none()
    if setting is None:
        raise ValueError(f"Provider '{provider}' not found")

    await db.delete(setting)
    await db.flush()
    return {"provider": provider, "deleted": True}


async def get_enabled_provider_config(db: AsyncSession, provider: str) -> dict | None:
    """
    获取已启用提供商的完整配置（含明文 API Key）供 AI 服务使用
    如果 DB 中不存在，回退到 .env 配置
    """
    result = await db.execute(
        select(ModelSettings).where(ModelSettings.provider == provider)
    )
    setting = result.scalar_one_or_none()

    if setting and setting.is_enabled == "true" and setting.api_key:
        return {
            "api_key": setting.api_key,
            "base_url": setting.base_url,
        }

    # 回退到 .env
    defaults = DEFAULT_PROVIDERS.get(provider, {})
    if defaults.get("api_key"):
        return defaults

    if provider == "ollama" and defaults.get("base_url"):
        return defaults

    return None


# ===========================================================================
# 节点类型可见性管理
# ===========================================================================

from ..models import ModelConfig
from .model_registry import _base_schemas, _custom_node_schemas
from .model_registry import register_custom_model, unregister_custom_model


async def get_model_visibility(db: AsyncSession) -> dict:
    """获取所有节点类型的可见性状态，按分类组织（含自定义节点，过滤已删除）"""
    full_schemas = _base_schemas()
    categories_data = full_schemas.get("categories", {})

    # 合并自定义节点到分类中
    for cat_key, models in _custom_node_schemas.items():
        if cat_key in categories_data:
            for model_id, node_def in models.items():
                categories_data[cat_key]["models"][model_id] = node_def

    # 从 DB 中读取已保存的可见性配置
    result = await db.execute(select(ModelConfig))
    configs = {c.model_id: c for c in result.scalars().all()}

    for cat_key, cat_data in list(categories_data.items()):
        models = cat_data.get("models", {})
        for model_id in list(models.keys()):
            config = configs.get(model_id)
            models[model_id]["is_visible"] = (
                config is None or config.is_visible == "true"
            )
            is_custom = model_id in (_custom_node_schemas.get(cat_key, {}))
            models[model_id]["is_custom"] = is_custom
            models[model_id]["is_deleted"] = (
                config is not None and config.is_deleted == "true"
            )
            # 过滤掉已软删除的模型
            if models[model_id]["is_deleted"]:
                del models[model_id]

    return categories_data


async def update_model_visibility(
    db: AsyncSession, model_id: str, is_visible: bool
) -> dict:
    """更新单个节点类型的显示/隐藏状态"""
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.model_id == model_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        # 从基础 schema 和自定义 schema 中找到模型所属分类
        base_schemas = _base_schemas()
        category = "unknown"
        for cat_key, cat_data in base_schemas.get("categories", {}).items():
            if model_id in cat_data.get("models", {}):
                category = cat_key
                break
        if category == "unknown":
            for cat_key, cat_models in _custom_node_schemas.items():
                if model_id in cat_models:
                    category = cat_key
                    break

        config = ModelConfig(
            model_id=model_id,
            category=category,
            is_visible="true" if is_visible else "false",
        )
        db.add(config)
    else:
        config.is_visible = "true" if is_visible else "false"

    await db.flush()
    await db.refresh(config)
    return {"model_id": config.model_id, "is_visible": config.is_visible == "true"}


async def update_category_visibility(
    db: AsyncSession, category: str, is_visible: bool
) -> dict:
    """批量更新一个分类下所有节点类型的可见性"""
    base_schemas = _base_schemas()
    models_in_category = base_schemas.get("categories", {}).get(category, {}).get("models", {})
    # 也包含自定义节点
    for model_id in _custom_node_schemas.get(category, {}):
        if model_id not in models_in_category:
            models_in_category[model_id] = _custom_node_schemas[category][model_id]

    updated = []
    for model_id in models_in_category:
        result = await db.execute(
            select(ModelConfig).where(ModelConfig.model_id == model_id)
        )
        config = result.scalar_one_or_none()

        if config is None:
            config = ModelConfig(
                model_id=model_id,
                category=category,
                is_visible="true" if is_visible else "false",
            )
            db.add(config)
        else:
            config.is_visible = "true" if is_visible else "false"
        updated.append(model_id)

    await db.flush()
    return {"category": category, "is_visible": is_visible, "updated": len(updated)}


# ===========================================================================
# 自定义节点 CRUD
# ===========================================================================

from ..models import CustomNodeSchema

_CATEGORY_INPUT_TEMPLATES = {
    "text": {
        "prompt": {"type": "string", "title": "Prompt", "description": "The text prompt"},
        "system_prompt": {"type": "string", "title": "System Prompt", "description": "System instructions"},
        "temperature": {"type": "number", "title": "Temperature", "default": 0.7, "minimum": 0, "maximum": 2},
        "max_tokens": {"type": "integer", "title": "Max Tokens", "default": 4096},
    },
    "image": {
        "prompt": {"type": "string", "title": "Prompt", "description": "Text prompt for image generation"},
        "width": {"type": "integer", "title": "Width", "default": 1024},
        "height": {"type": "integer", "title": "Height", "default": 1024},
        "num_outputs": {"type": "integer", "title": "Count", "default": 1},
    },
    "video": {
        "prompt": {"type": "string", "title": "Prompt", "description": "Text prompt for video generation"},
        "image_url": {"type": "string", "title": "Input Image URL", "description": "Source image for I2V"},
        "duration": {"type": "integer", "title": "Duration (s)", "default": 5},
    },
    "audio": {
        "prompt": {"type": "string", "title": "Prompt", "description": "Text to generate audio from"},
    },
    "utility": {
        "prompt": {"type": "string", "title": "Prompt"},
    },
}


def _build_input_schema(properties: dict, required: list[str] = None) -> dict:
    return {
        "schemas": {
            "input_data": {
                "properties": properties,
                "required": required or list(properties.keys()),
            }
        }
    }


async def create_custom_node(db: AsyncSession, data: dict) -> dict:
    """创建自定义节点类型"""
    model_id = (data.get("model_id") or "").strip()
    if not model_id:
        raise ValueError("model_id is required")

    # 检查是否与已有模型冲突
    base_schemas = _base_schemas()
    if model_id in base_schemas.get("categories", {}).get(data.get("category", ""), {}).get("models", {}):
        raise ValueError(f"Model '{model_id}' already exists in built-in schemas")
    if model_id in _custom_node_schemas.get(data.get("category", ""), {}):
        raise ValueError(f"Custom model '{model_id}' already exists")

    result = await db.execute(
        select(CustomNodeSchema).where(CustomNodeSchema.model_id == model_id)
    )
    if result.scalar_one_or_none():
        raise ValueError(f"Custom model '{model_id}' already exists in database")

    category = data.get("category", "utility")
    name = data.get("name", model_id)
    service = data.get("service", "openai")

    # 自动生成 input_schema
    props = _CATEGORY_INPUT_TEMPLATES.get(category, _CATEGORY_INPUT_TEMPLATES["utility"])
    input_schema = _build_input_schema(props)

    node_schema = CustomNodeSchema(
        model_id=model_id,
        category=category,
        name=name,
        service=service,
        input_schema=input_schema,
    )
    db.add(node_schema)
    await db.flush()
    await db.refresh(node_schema)

    # 同步到内存注册表
    node_def = {"name": name, "input_schema": input_schema}
    register_custom_model(model_id, service, category, node_def)

    return {
        "model_id": node_schema.model_id,
        "category": node_schema.category,
        "name": node_schema.name,
        "service": node_schema.service,
        "input_schema": node_schema.input_schema,
    }


async def update_custom_node(db: AsyncSession, model_id: str, data: dict) -> dict:
    """更新自定义节点类型"""
    result = await db.execute(
        select(CustomNodeSchema).where(CustomNodeSchema.model_id == model_id)
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise ValueError(f"Custom model '{model_id}' not found")

    old_category = node.category

    if "name" in data:
        node.name = data["name"]
    if "service" in data:
        node.service = data["service"]
    if "category" in data and data["category"] != old_category:
        new_cat = data["category"]
        props = _CATEGORY_INPUT_TEMPLATES.get(new_cat, _CATEGORY_INPUT_TEMPLATES["utility"])
        node.category = new_cat
        node.input_schema = _build_input_schema(props)
    if "input_schema" in data:
        node.input_schema = data["input_schema"]

    await db.flush()
    await db.refresh(node)

    # 更新内存注册表
    unregister_custom_model(model_id)
    node_def = {"name": node.name, "input_schema": node.input_schema}
    register_custom_model(node.model_id, node.service, node.category, node_def)

    return {
        "model_id": node.model_id,
        "category": node.category,
        "name": node.name,
        "service": node.service,
        "input_schema": node.input_schema,
    }


async def delete_custom_node(db: AsyncSession, model_id: str) -> dict:
    """删除自定义节点类型"""
    result = await db.execute(
        select(CustomNodeSchema).where(CustomNodeSchema.model_id == model_id)
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise ValueError(f"Custom model '{model_id}' not found")

    await db.delete(node)

    # 同时删除关联的 ModelConfig
    config_result = await db.execute(
        select(ModelConfig).where(ModelConfig.model_id == model_id)
    )
    config = config_result.scalar_one_or_none()
    if config:
        await db.delete(config)

    await db.flush()

    # 从内存注册表移除
    unregister_custom_model(model_id)

    return {"model_id": model_id, "deleted": True}


# ===========================================================================
# 内置模型 软删除 / 恢复
# ===========================================================================

async def soft_delete_model(db: AsyncSession, model_id: str) -> dict:
    """软删除一个模型（统一通过 ModelConfig 标记删除，不物理删除）"""
    # 检查模型是否存在（基础 Schema 或 自定义 Schema）
    base_schemas = _base_schemas()
    exists = False
    for cat_data in base_schemas.get("categories", {}).values():
        if model_id in cat_data.get("models", {}):
            exists = True
            break
    if not exists:
        for cat_models in _custom_node_schemas.values():
            if model_id in cat_models:
                exists = True
                break

    if not exists:
        raise ValueError(f"Model '{model_id}' not found")

    # 所有模型统一：通过 ModelConfig 标记软删除
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.model_id == model_id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        # 找到所属分类
        category = "unknown"
        for cat_key, cat_data in base_schemas.get("categories", {}).items():
            if model_id in cat_data.get("models", {}):
                category = cat_key
                break
        if category == "unknown":
            for cat_key, cat_models in _custom_node_schemas.items():
                if model_id in cat_models:
                    category = cat_key
                    break
        config = ModelConfig(model_id=model_id, category=category)

    config.is_visible = "false"
    config.is_deleted = "true"
    if config.id is None:
        db.add(config)

    await db.flush()
    await db.refresh(config)
    return {"model_id": model_id, "deleted": True}


async def restore_model(db: AsyncSession, model_id: str) -> dict:
    """恢复一个已软删除的模型"""
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.model_id == model_id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise ValueError(f"No deleted model found for '{model_id}'")

    config.is_deleted = "false"
    config.is_visible = "true"
    await db.flush()
    return {"model_id": model_id, "restored": True}


async def get_deleted_models(db: AsyncSession) -> dict:
    """获取所有已软删除的模型（用于前端恢复面板）"""
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.is_deleted == "true")
    )
    deleted = result.scalars().all()

    base_schemas = _base_schemas()
    models = {}
    for config in deleted:
        found = False
        # 搜索基础 schema
        for cat_data in base_schemas.get("categories", {}).values():
            model = cat_data.get("models", {}).get(config.model_id)
            if model:
                models[config.model_id] = {
                    "name": model.get("name", config.model_id),
                    "category": config.category,
                }
                found = True
                break
        # 搜索自定义 schema
        if not found:
            for cat_models in _custom_node_schemas.values():
                model = cat_models.get(config.model_id)
                if model:
                    models[config.model_id] = {
                        "name": model.get("name", config.model_id),
                        "category": config.category,
                    }
                    found = True
                    break
        # 也未找到 → 使用 model_id 作为名称
        if not found:
            models[config.model_id] = {
                "name": config.model_id,
                "category": config.category,
            }
    return {"deleted_models": models}
