"""通道管理服务层"""

from __future__ import annotations
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Channel, ModelRoute
from ..schemas import ChannelCreate, ChannelUpdate


async def list_channels(db: AsyncSession) -> tuple[list[dict], int]:
    """列出所有通道，附带路由数统计"""
    result = await db.execute(
        select(Channel).order_by(Channel.created_at.desc())
    )
    channels = result.scalars().all()

    items = []
    for ch in channels:
        count_result = await db.execute(
            select(func.count(ModelRoute.id)).where(ModelRoute.channel_id == ch.id)
        )
        route_count = count_result.scalar() or 0
        items.append({
            "id": ch.id,
            "name": ch.name,
            "display_name": ch.display_name,
            "provider_type": ch.provider_type,
            "base_url": ch.base_url,
            "default_model": ch.default_model,
            "status": ch.status,
            "metadata": ch.metadata_,
            "route_count": route_count,
            "created_at": ch.created_at.isoformat() if ch.created_at else "",
            "updated_at": ch.updated_at.isoformat() if ch.updated_at else "",
        })

    return items, len(items)


async def get_channel(db: AsyncSession, channel_id: str) -> dict | None:
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    ch = result.scalar_one_or_none()
    if not ch:
        return None
    return {
        "id": ch.id, "name": ch.name, "display_name": ch.display_name,
        "provider_type": ch.provider_type, "base_url": ch.base_url,
        "api_key": ch.api_key, "default_model": ch.default_model,
        "status": ch.status, "metadata": ch.metadata_,
        "created_at": ch.created_at.isoformat() if ch.created_at else "",
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else "",
    }


async def create_channel(db: AsyncSession, data: ChannelCreate) -> Channel:
    ch = Channel(
        name=data.name,
        display_name=data.display_name,
        provider_type=data.provider_type,
        base_url=data.base_url,
        api_key=data.api_key,
        default_model=data.default_model,
        metadata_=data.metadata_ or {},
    )
    db.add(ch)
    await db.flush()
    return ch


async def update_channel(db: AsyncSession, channel_id: str, data: ChannelUpdate) -> Channel | None:
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    ch = result.scalar_one_or_none()
    if not ch:
        return None
    update_data = data.model_dump(exclude_unset=True, by_alias=True)
    # metadata_ field maps from 'metadata' alias
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")
    for key, value in update_data.items():
        if hasattr(ch, key) and value is not None:
            setattr(ch, key, value)
    await db.flush()
    return ch


async def delete_channel(db: AsyncSession, channel_id: str) -> bool:
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    ch = result.scalar_one_or_none()
    if not ch:
        return False
    # 级联删除关联的路由
    await db.execute(
        select(ModelRoute).where(ModelRoute.channel_id == channel_id)
    )
    routes = (await db.execute(
        select(ModelRoute).where(ModelRoute.channel_id == channel_id)
    )).scalars().all()
    for route in routes:
        await db.delete(route)
    await db.delete(ch)
    await db.flush()
    return True
