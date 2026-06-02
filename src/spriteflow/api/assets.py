"""素材 API — 上传、查询、详情+血缘

所有响应中的 uri/thumbnail 都返回为 COS 预签名 URL（24h 有效），
方便前端直接用于 <img src=...>；底层 cos:// 路径不暴露给前端。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Form
from pydantic import BaseModel

from .deps import get_db, get_storage
from ..asset_hub.ingest import IngestPipeline
from ..asset_hub.models import Asset

router = APIRouter()


class AssetResponse(BaseModel):
    """素材响应（uri/thumbnail 已转为预签名 URL）"""

    id: str
    type: str
    source: str
    uri: str
    hash: str
    width: int | None = None
    height: int | None = None
    thumbnail: str | None = None
    tags: list[str] = []
    parent_id: str | None = None
    provenance: dict | None = None
    favorite: bool = False
    created_at: str


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int


async def _asset_to_response(asset: Asset) -> AssetResponse:
    storage = get_storage()
    uri = asset.uri
    thumb = asset.thumbnail
    try:
        uri = await storage.get_presigned_url(asset.uri, expires=86400)
        if asset.thumbnail:
            thumb = await storage.get_presigned_url(asset.thumbnail, expires=86400)
    except Exception:
        # 本地存储或签名失败时退回原值
        pass

    return AssetResponse(
        id=asset.id,
        type=asset.type,
        source=asset.source,
        uri=uri,
        hash=asset.hash,
        width=asset.width,
        height=asset.height,
        thumbnail=thumb,
        tags=asset.tags,
        parent_id=asset.parent_id,
        provenance=asset.provenance,
        favorite=asset.favorite,
        created_at=asset.created_at,
    )


@router.get("/assets", response_model=AssetListResponse)
async def list_assets(
    source: str | None = None,
    tags: str | None = None,
    favorite: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """查询素材列表，支持按 source / tags / favorite 筛选"""
    db = get_db()
    tag_list = tags.split(",") if tags else None
    assets = await db.list_assets(
        source=source, tags=tag_list, favorite=favorite, limit=limit, offset=offset
    )
    items = [await _asset_to_response(a) for a in assets]
    return AssetListResponse(items=items, total=len(items))


@router.post("/assets", response_model=AssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    tags: str = Form(""),
    parent_id: str | None = Form(None),
):
    """上传素材（走 Ingest Pipeline → COS）"""
    db = get_db()
    storage = get_storage()

    data = await file.read()
    tag_list = tags.split(",") if tags else []

    pipeline = IngestPipeline(storage, db)
    asset = await pipeline.ingest(
        data=data,
        filename=file.filename or "",
        source="uploaded",
        tags=tag_list,
        parent_id=parent_id,
    )

    return await _asset_to_response(asset)


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str):
    db = get_db()
    asset = await db.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")
    return await _asset_to_response(asset)


@router.get("/assets/{asset_id}/children", response_model=AssetListResponse)
async def get_asset_children(asset_id: str):
    db = get_db()
    children = await db.get_children(asset_id)
    items = [await _asset_to_response(a) for a in children]
    return AssetListResponse(items=items, total=len(items))


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str):
    db = get_db()
    success = await db.delete_asset(asset_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")
    return {"status": "deleted"}
