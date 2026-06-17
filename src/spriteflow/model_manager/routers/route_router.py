"""模型路由管理 API 路由"""

from __future__ import annotations
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import (
    ModelRouteCreate, ModelRouteUpdate, RouteResponse,
    ModelRoutesPayload, ModelWithRoutes,
    ModelListResponse, RegistryListResponse,
    ModelDefaultUpdate, ModelDefaultsResponse,
)
from ..services.route_service import (
    list_all_models_with_routes, set_model_routes, get_model_registry,
    add_route, update_route, delete_route,
    get_defaults, set_default,
)

router = APIRouter()


@router.get("/models", response_model=ModelListResponse)
async def api_list_models(
    search: str = Query(""),
    category: str = Query(""),
    subcategory: str = Query(""),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    registry = await get_model_registry()
    items, total, offset, limit = await list_all_models_with_routes(
        db, registry, search, category, subcategory, offset, limit,
    )
    return ModelListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/registry", response_model=RegistryListResponse)
async def api_get_registry():
    registry = await get_model_registry()
    return RegistryListResponse(items=registry, total=len(registry))


@router.get("/models/{model_id:path}", response_model=ModelWithRoutes)
async def api_get_model(model_id: str, db: AsyncSession = Depends(get_db)):
    registry = await get_model_registry()
    model_info = None
    for m in registry:
        if m["model_id"] == model_id:
            model_info = m
            break
    if not model_info:
        raise HTTPException(status_code=404, detail="模型不存在")

    items, _, _, _ = await list_all_models_with_routes(db, [model_info])
    if not items:
        return ModelWithRoutes(**model_info, routes=[])
    return ModelWithRoutes(**items[0])


@router.put("/models/{model_id:path}/routes", response_model=list[RouteResponse])
async def api_set_model_routes(
    model_id: str,
    data: ModelRoutesPayload,
    db: AsyncSession = Depends(get_db),
):
    routes = await set_model_routes(db, model_id, data)
    return routes


@router.post("/models/{model_id:path}/routes", response_model=RouteResponse)
async def api_add_route(
    model_id: str,
    data: ModelRouteCreate,
    db: AsyncSession = Depends(get_db),
):
    route = await add_route(db, model_id, data)
    return route


@router.patch("/models/{model_id:path}/routes/{route_id}", response_model=RouteResponse)
async def api_update_route(
    model_id: str,
    route_id: str,
    data: ModelRouteUpdate,
    db: AsyncSession = Depends(get_db),
):
    route = await update_route(db, route_id, data)
    if not route:
        raise HTTPException(status_code=404, detail="路由不存在")
    return route


@router.delete("/models/{model_id:path}/routes/{route_id}")
async def api_delete_route(
    model_id: str,
    route_id: str,
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_route(db, route_id)
    if not ok:
        raise HTTPException(status_code=404, detail="路由不存在")
    return {"status": "deleted"}


# ---- 默认模型管理 ----

@router.get("/defaults", response_model=ModelDefaultsResponse)
async def api_get_defaults(db: AsyncSession = Depends(get_db)):
    """获取所有分类的默认模型配置"""
    defaults = await get_defaults(db)
    return ModelDefaultsResponse(defaults=defaults)


@router.put("/defaults/{category}", response_model=ModelDefaultsResponse)
async def api_set_default(
    category: str,
    data: ModelDefaultUpdate,
    subcategory: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """设置某分类（及可选子分类）的默认模型"""
    try:
        defaults = await set_default(db, category, data.model_id, subcategory)
        return ModelDefaultsResponse(defaults=defaults)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
