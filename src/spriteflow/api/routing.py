"""路由配置 API — 读写能力路由表（持久化到数据库）"""

from __future__ import annotations

import json

from fastapi import APIRouter

from .deps import get_router, get_db

router = APIRouter()


@router.get("/routing")
async def get_routing():
    """获取当前路由配置"""
    router_instance = get_router()
    return {
        "routes": router_instance.get_routes(),
        "fallback": router_instance.get_fallbacks(),
        "providers": [
            {"name": p.name, "capabilities": [c.value for c in p.capabilities]}
            for p in router_instance._providers.values()
        ],
    }


@router.put("/routing")
async def update_routing(payload: dict):
    """更新路由映射 + 回退链，持久化到数据库

    payload: {
        "routes": {"text2img": "seedream", ...},
        "fallback": {"text2img": ["openrouter"], ...}
    }
    """
    router_instance = get_router()
    db = get_db()
    changed = False

    routes = payload.get("routes")
    if isinstance(routes, dict):
        for cap, provider_name in routes.items():
            if isinstance(cap, str) and isinstance(provider_name, str):
                router_instance.update_route(cap, provider_name)
                changed = True

    fallback = payload.get("fallback")
    if isinstance(fallback, dict):
        for cap, chain in fallback.items():
            if isinstance(cap, str) and isinstance(chain, list):
                router_instance.update_fallback(cap, [str(x) for x in chain])
                changed = True

    if changed:
        # 持久化到数据库
        db_items: dict[str, str] = {}
        for cap, prov in router_instance.get_routes().items():
            db_items[f"route:{cap}"] = prov
        for cap, chain in router_instance.get_fallbacks().items():
            db_items[f"fallback:{cap}"] = json.dumps(chain)
        await db.set_configs_batch(db_items)

    return {
        "status": "ok",
        "routes": router_instance.get_routes(),
        "fallback": router_instance.get_fallbacks(),
    }

