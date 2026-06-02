"""路由配置 API — 读写能力路由表"""

from __future__ import annotations

from fastapi import APIRouter

from .deps import get_router

router = APIRouter()


@router.get("/routing")
async def get_routing():
    """获取当前路由配置"""
    router_instance = get_router()
    routes = router_instance.get_routes()
    return {
        "routes": routes,
        "providers": [
            {"name": p.name, "capabilities": [c.value for c in p.capabilities]}
            for p in router_instance._providers.values()
        ],
    }


@router.put("/routing")
async def update_routing(routes: dict[str, str]):
    """更新路由映射"""
    router_instance = get_router()
    for cap, provider_name in routes.items():
        router_instance.update_route(cap, provider_name)
    return {"status": "updated", "routes": router_instance.get_routes()}
