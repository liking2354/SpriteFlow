"""模型路由管理服务层"""

from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import ModelRoute, Channel
from ..schemas import ModelRouteCreate, ModelRouteUpdate, ModelRoutesPayload


def _route_to_dict(r: ModelRoute, channels: dict) -> dict:
    ch = channels.get(r.channel_id)
    return {
        "id": r.id, "model_id": r.model_id, "channel_id": r.channel_id,
        "channel_name": ch.name if ch else "",
        "channel_display_name": ch.display_name if ch else "",
        "priority": r.priority, "model_override": r.model_override,
        "param_overrides": r.param_overrides or {}, "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
    }


async def list_all_models_with_routes(
    db: AsyncSession,
    model_registry: list[dict],
    search: str = "",
    category: str = "",
    subcategory: str = "",
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[dict], int]:
    """列出所有模型及其路由配置（支持分页）"""
    # 获取所有路由
    route_result = await db.execute(
        select(ModelRoute).order_by(ModelRoute.priority.asc())
    )
    all_routes = route_result.scalars().all()

    # 获取所有通道（用于填充 channel_name）
    ch_result = await db.execute(select(Channel))
    channels = {ch.id: ch for ch in ch_result.scalars().all()}

    # 获取默认模型配置
    from ..models import ModelDefault
    default_result = await db.execute(select(ModelDefault))
    defaults: dict[str, str] = {(d.category, d.subcategory): d.model_id for d in default_result.scalars().all()}

    # 构建 model_id → routes 映射
    route_map: dict[str, list[dict]] = {}
    for r in all_routes:
        route_map.setdefault(r.model_id, []).append(_route_to_dict(r, channels))

    # 过滤模型
    items = []
    for m in model_registry:
        mid = m.get("model_id", m.get("id", ""))
        if search and search.lower() not in mid.lower() and search.lower() not in m.get("name", "").lower():
            continue
        if category and m.get("category", "") != category:
            continue
        if subcategory and m.get("subcategory", "") != subcategory:
            continue
        m_cat = m.get("category", "")
        m_sub = m.get("subcategory", "")
        items.append({
            "model_id": mid,
            "name": m.get("name", mid),
            "category": m_cat,
            "subcategory": m_sub,
            "service": m.get("service", ""),
            "routes": route_map.get(mid, []),
            "is_default": defaults.get((m_cat, m_sub)) == mid,
        })

    total = len(items)
    # 分页切片
    paginated = items[offset:offset + limit]

    return paginated, total, offset, limit


async def set_model_routes(
    db: AsyncSession,
    model_id: str,
    data: ModelRoutesPayload,
) -> list[dict]:
    """批量设置某模型的所有路由（先删后建）"""
    # 删除旧路由
    old = (await db.execute(
        select(ModelRoute).where(ModelRoute.model_id == model_id)
    )).scalars().all()
    for r in old:
        await db.delete(r)

    # 创建新路由
    routes = []
    for route_data in data.routes:
        r = ModelRoute(
            model_id=model_id,
            channel_id=route_data.channel_id,
            priority=route_data.priority,
            model_override=route_data.model_override,
            param_overrides=route_data.param_overrides,
            status=route_data.status,
        )
        db.add(r)
        routes.append(r)

    await db.flush()

    # 获取通道名
    ch_result = await db.execute(select(Channel))
    channels = {ch.id: ch for ch in ch_result.scalars().all()}

    return [_route_to_dict(r, channels) for r in routes]


async def add_route(
    db: AsyncSession,
    model_id: str,
    data: ModelRouteCreate,
) -> dict:
    """添加单条路由"""
    r = ModelRoute(
        model_id=model_id,
        channel_id=data.channel_id,
        priority=data.priority,
        model_override=data.model_override,
        param_overrides=data.param_overrides,
        status=data.status,
    )
    db.add(r)
    await db.flush()

    ch_result = await db.execute(select(Channel).where(Channel.id == r.channel_id))
    ch = ch_result.scalar_one_or_none()
    channels = {r.channel_id: ch} if ch else {}
    return _route_to_dict(r, channels)


async def update_route(
    db: AsyncSession,
    route_id: str,
    data: ModelRouteUpdate,
) -> dict | None:
    """更新单条路由（使用原生 UPDATE 避免 SQLite async greenlet 问题）"""
    from sqlalchemy import update as sa_update
    from datetime import datetime, timezone

    # 先查是否存在
    result = await db.execute(select(ModelRoute).where(ModelRoute.id == route_id))
    r = result.scalar_one_or_none()
    if not r:
        return None

    # 构建更新字段
    values = {"updated_at": datetime.now(timezone.utc)}
    if data.priority is not None:
        values["priority"] = data.priority
    if data.model_override is not None:
        values["model_override"] = data.model_override
    if data.param_overrides is not None:
        values["param_overrides"] = data.param_overrides
    if data.status is not None:
        values["status"] = data.status

    if len(values) > 1:  # 除了 updated_at 还有别的
        await db.execute(sa_update(ModelRoute).where(ModelRoute.id == route_id).values(**values))
        await db.flush()
        # 重新查询以获得更新后的信息
        result = await db.execute(select(ModelRoute).where(ModelRoute.id == route_id))
        r = result.scalar_one_or_none()

    ch_result = await db.execute(select(Channel).where(Channel.id == r.channel_id))
    ch = ch_result.scalar_one_or_none()
    channels = {r.channel_id: ch} if ch else {}
    return _route_to_dict(r, channels)


async def delete_route(db: AsyncSession, route_id: str) -> bool:
    """删除单条路由"""
    result = await db.execute(select(ModelRoute).where(ModelRoute.id == route_id))
    r = result.scalar_one_or_none()
    if not r:
        return False
    await db.delete(r)
    await db.flush()
    return True


async def get_model_registry() -> list[dict]:
    """获取所有已知模型注册表（AI 模型，不含 passthrough / utility / 软删除节点）"""
    from ...workflow.services.model_registry import _base_schemas, _custom_node_schemas
    from ...workflow.services.model_registry import MODEL_REGISTRY, _derive_subcategory
    from ...workflow.database import async_session as wf_session
    from ...workflow.models import ModelConfig as WFModelConfig
    from sqlalchemy import select as sa_select

    # 查询工作流数据库中软删除的模型 ID 集合
    deleted_ids: set[str] = set()
    async with wf_session() as wf_db:
        result = await wf_db.execute(
            sa_select(WFModelConfig.model_id).where(WFModelConfig.is_deleted == "true")
        )
        deleted_ids = set(row[0] for row in result.fetchall())

    schemas = _base_schemas()
    models = []

    # 过滤：跳过 utility 分类、passthrough 节点、软删除模型
    for cat_key, cat_data in schemas.get("categories", {}).items():
        if cat_key == "utility":
            continue
        for model_id, node_def in cat_data.get("models", {}).items():
            service = MODEL_REGISTRY.get(model_id, "")
            if service == "passthrough":
                continue
            if model_id in deleted_ids:
                continue
            # 为 image/video 内置模型推导子分类
            subcategory = _derive_subcategory(model_id) if cat_key in ("image", "video") else ""
            models.append({
                "model_id": model_id,
                "name": node_def.get("name", model_id),
                "category": cat_key,
                "subcategory": subcategory,
                "service": service,
            })

    # AI 模型（内置 + 自定义）：统一从 DB 加载到 _custom_node_schemas
    for cat_key, cat_models in _custom_node_schemas.items():
        if cat_key == "utility":
            continue
        for model_id, node_def in cat_models.items():
            service = MODEL_REGISTRY.get(model_id, "")
            if service == "passthrough":
                continue
            if model_id in deleted_ids:
                continue
            models.append({
                "model_id": model_id,
                "name": node_def.get("name", model_id),
                "category": cat_key,
                "subcategory": node_def.get("subcategory", ""),
                "service": service,
            })

    return models


def _defaults_key(category: str, subcategory: str = "") -> str:
    """构建默认模型映射的复合键：category:subcategory 或仅 category"""
    return f"{category}:{subcategory}" if subcategory else category


async def get_defaults(db: AsyncSession) -> dict[str, str]:
    """获取所有分类的默认模型映射"""
    from ..models import ModelDefault
    result = await db.execute(select(ModelDefault))
    return {_defaults_key(d.category, d.subcategory): d.model_id for d in result.scalars().all()}


async def set_default(db: AsyncSession, category: str, model_id: str, subcategory: str = "") -> dict[str, str]:
    """设置某分类（及可选子分类）的默认模型（upsert）"""
    from ..models import ModelDefault
    from sqlalchemy import update as sa_update, insert as sa_insert

    # 检查模型是否存在
    registry = await get_model_registry()
    found = any(
        m["model_id"] == model_id and m["category"] == category and m.get("subcategory", "") == subcategory
        for m in registry
    )
    if not found:
        detail = f"模型 {model_id} 不存在或不属于 {category}"
        if subcategory:
            detail += f":{subcategory}"
        detail += " 分类"
        raise ValueError(detail)

    # upsert: 先 update，若影响 0 行则 insert
    affected = await db.execute(
        sa_update(ModelDefault)
        .where(ModelDefault.category == category, ModelDefault.subcategory == subcategory)
        .values(model_id=model_id)
    )
    if affected.rowcount == 0:
        default = ModelDefault(category=category, subcategory=subcategory, model_id=model_id)
        db.add(default)

    await db.flush()
    return await get_defaults(db)


async def get_default_text_model_config(db: AsyncSession) -> dict | None:
    """
    获取 text 分类的默认模型通道配置（供 AI 工作流 Architect 使用）
    返回 None 表示未配置或无可用的路由/通道
    """
    defaults = await get_defaults(db)
    model_id = defaults.get("text")
    if not model_id:
        return None

    # 获取该模型最高优先级的 active 路由
    result = await db.execute(
        select(ModelRoute)
        .where(ModelRoute.model_id == model_id, ModelRoute.status == "active")
        .order_by(ModelRoute.priority.asc())
        .limit(1)
    )
    route = result.scalar_one_or_none()
    if not route:
        return None

    # 获取通道配置
    ch_result = await db.execute(select(Channel).where(Channel.id == route.channel_id))
    channel = ch_result.scalar_one_or_none()
    if not channel or channel.status != "active":
        return None

    # 确定实际使用的模型名：model_override > channel.default_model > model_id
    actual_model = route.model_override or channel.default_model or model_id

    return {
        "api_key": channel.api_key,
        "base_url": channel.base_url or "https://api.openai.com/v1",
        "model": actual_model,
        "model_id": model_id,
        "channel_name": channel.display_name,
    }


async def get_model_channel_config(db: AsyncSession, model_id: str) -> dict | None:
    """
    获取指定模型（任意 model_id）的最高优先级 active 路由的通道配置
    返回 None 表示该模型未配置或无可用的路由/通道
    """
    result = await db.execute(
        select(ModelRoute)
        .where(ModelRoute.model_id == model_id, ModelRoute.status == "active")
        .order_by(ModelRoute.priority.asc())
        .limit(1)
    )
    route = result.scalar_one_or_none()
    if not route:
        return None

    ch_result = await db.execute(select(Channel).where(Channel.id == route.channel_id))
    channel = ch_result.scalar_one_or_none()
    if not channel or channel.status != "active":
        return None

    actual_model = route.model_override or channel.default_model or model_id

    return {
        "api_key": channel.api_key,
        "base_url": channel.base_url or "https://api.openai.com/v1",
        "model": actual_model,
        "model_id": model_id,
        "channel_name": channel.display_name,
    }
