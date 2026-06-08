"""Provider 配置 API — 运行时读写模型/端点/密钥（持久化到数据库）"""

from __future__ import annotations

from fastapi import APIRouter

from .deps import get_router, get_db

router = APIRouter()


@router.get("/config")
async def get_config():
    """获取所有 provider 的当前配置"""
    router_instance = get_router()
    provider_configs = router_instance.get_provider_configs()

    # 对 api_key 做脱敏处理
    result: dict[str, dict] = {}
    for name, cfg in provider_configs.items():
        item = dict(cfg)
        has_key = item.pop("api_key_configured", False)
        item["api_key_masked"] = _mask_key(router_instance._credentials.get(name, ""))
        item["api_key_configured"] = has_key
        result[name] = item

    return {"providers": result}


@router.put("/config")
async def update_config(payload: dict):
    """更新 provider 配置（模型/端点/密钥），持久化到数据库

    payload: {
        "providers": {
            "openrouter": {
                "model": "openai/gpt-image-1",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-..."           // 可选，空字符串 = 不更新
            },
            "seedream": { "model": "...", "base_url": "..." },
            "seedance": { "model": "...", "base_url": "..." }
        }
    }
    """
    router_instance = get_router()
    db = get_db()
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return {"status": "error", "detail": "providers 字段必须为 dict"}

    updated: list[str] = []
    db_items: dict[str, str] = {}

    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        if name not in router_instance._providers:
            continue

        # 更新 api_key → 内存 + 数据库
        api_key = cfg.get("api_key")
        if isinstance(api_key, str) and api_key:
            router_instance.update_credential(name, api_key)
            db_items[f"credential:{name}"] = api_key
            updated.append(f"{name}.api_key")

        # 更新 model → 内存 + 数据库
        model = cfg.get("model")
        if isinstance(model, str) and model:
            router_instance.update_provider_model(name, model)
            db_items[f"provider:{name}:model"] = model
            updated.append(f"{name}.model")

        # 更新 base_url → 内存 + 数据库
        base_url = cfg.get("base_url")
        if isinstance(base_url, str) and base_url:
            router_instance.update_provider_base_url(name, base_url)
            db_items[f"provider:{name}:base_url"] = base_url
            updated.append(f"{name}.base_url")

    if db_items:
        await db.set_configs_batch(db_items)

    return {"status": "ok", "updated": updated}


def _mask_key(key: str) -> str:
    """对 API Key 做脱敏：sk-****xxxx"""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "****"
    return key[:3] + "****" + key[-4:]
