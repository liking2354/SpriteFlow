"""通道管理 API 路由"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import (
    ChannelCreate, ChannelUpdate, ChannelResponse,
    ChannelListResponse, ChannelTestResult,
)
from ..services.channel_service import (
    list_channels, get_channel, create_channel,
    update_channel, delete_channel,
)

router = APIRouter()


@router.get("/channels", response_model=ChannelListResponse)
async def api_list_channels(db: AsyncSession = Depends(get_db)):
    items, total = await list_channels(db)
    return ChannelListResponse(items=items, total=total)


@router.post("/channels", response_model=ChannelResponse)
async def api_create_channel(data: ChannelCreate, db: AsyncSession = Depends(get_db)):
    ch = await create_channel(db, data)
    return ChannelResponse(
        id=ch.id, name=ch.name, display_name=ch.display_name,
        provider_type=ch.provider_type, base_url=ch.base_url,
        default_model=ch.default_model, status=ch.status,
        metadata=ch.metadata_, route_count=0,
        created_at=ch.created_at.isoformat() if ch.created_at else "",
        updated_at=ch.updated_at.isoformat() if ch.updated_at else "",
    )


@router.get("/channels/{channel_id}", response_model=ChannelResponse)
async def api_get_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    ch = await get_channel(db, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")
    return ChannelResponse(**ch, route_count=0)


@router.put("/channels/{channel_id}", response_model=ChannelResponse)
async def api_update_channel(
    channel_id: str, data: ChannelUpdate, db: AsyncSession = Depends(get_db)
):
    ch = await update_channel(db, channel_id, data)
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")
    return ChannelResponse(
        id=ch.id, name=ch.name, display_name=ch.display_name,
        provider_type=ch.provider_type, base_url=ch.base_url,
        default_model=ch.default_model, status=ch.status,
        metadata=ch.metadata_, route_count=0,
        created_at=ch.created_at.isoformat() if ch.created_at else "",
        updated_at=ch.updated_at.isoformat() if ch.updated_at else "",
    )


@router.delete("/channels/{channel_id}")
async def api_delete_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    ok = await delete_channel(db, channel_id)
    if not ok:
        raise HTTPException(status_code=404, detail="通道不存在")
    return {"status": "deleted"}


@router.post("/channels/{channel_id}/test", response_model=ChannelTestResult)
async def api_test_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    """测试通道连接（支持 provider-specific 实现）"""
    import time

    ch = await get_channel(db, channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")

    from ..providers import get_provider, ChannelConfig, TestResult

    provider_type = ch.get("provider_type", "")
    provider_cls: type | None = None

    # 尝试加载 provider-specific 实现
    from ..providers import PROVIDER_REGISTRY
    provider_cls = PROVIDER_REGISTRY.get(provider_type)

    if provider_cls:
        # 使用专用 provider 实现
        provider = provider_cls()
        config = ChannelConfig(
            name=ch["name"],
            provider_type=provider_type,
            base_url=ch.get("base_url", "") or provider.default_base_url(),
            api_key=ch.get("api_key", ""),
            default_model=ch.get("default_model", ""),
            metadata=ch.get("metadata", {}),
        )
        result = await provider.test_connection(config)
        return ChannelTestResult(
            success=result.success,
            message=result.message,
            latency_ms=result.latency_ms,
        )

    # 降级：通用 HTTP 测试
    import httpx

    base_url = ch["base_url"]
    api_key = ch.get("api_key", "")

    if not base_url:
        return ChannelTestResult(success=False, message="未配置 Base URL")

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        t0 = time.time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(base_url.rstrip("/") + "/models", headers=headers)
        latency = (time.time() - t0) * 1000
        if resp.status_code < 500:
            return ChannelTestResult(
                success=True,
                message=f"连接成功 (HTTP {resp.status_code})",
                latency_ms=round(latency, 1),
            )
        else:
            return ChannelTestResult(
                success=False,
                message=f"服务器返回 {resp.status_code}",
                latency_ms=round(latency, 1),
            )
    except Exception as e:
        return ChannelTestResult(success=False, message=f"连接失败: {str(e)}")
