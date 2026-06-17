"""素材 API — 上传、查询、详情+血缘

所有响应中的 uri/thumbnail 都返回为 COS 预签名 URL（24h 有效），
方便前端直接用于 <img src=...>；底层 cos:// 路径不暴露给前端。
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

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
    group_id: str | None = None
    provenance: dict | None = None
    favorite: bool = False
    text_preview: str | None = None
    duration: float | None = None
    mime_type: str | None = None
    created_at: str


class GroupResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: str


class GroupListResponse(BaseModel):
    items: list[GroupResponse]


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int


async def _asset_to_response(asset: Asset) -> AssetResponse:
    storage = get_storage()
    uri = asset.uri
    thumb = asset.thumbnail
    from ..storage.local_storage import LocalStorage
    if isinstance(storage, LocalStorage):
        # 本地存储：返回代理 URL，浏览器走服务端代理加载
        uri = f"/api/assets/{asset.id}/raw"
        thumb = f"/api/assets/{asset.id}/raw?thumb=1" if asset.thumbnail else None
    else:
        try:
            uri = await storage.get_presigned_url(asset.uri, expires=86400)
            if asset.thumbnail:
                thumb = await storage.get_presigned_url(asset.thumbnail, expires=86400)
        except Exception:
            # 签名失败时退回原值
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
        group_id=asset.group_id,
        provenance=asset.provenance,
        favorite=asset.favorite,
        text_preview=asset.text_preview,
        duration=asset.duration,
        mime_type=asset.mime_type,
        created_at=asset.created_at,
    )


@router.get("/assets", response_model=AssetListResponse)
async def list_assets(
    source: str | None = None,
    tags: str | None = None,
    favorite: bool | None = None,
    group_id: str | None = None,
    type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """查询素材列表，支持按 source / tags / favorite / group_id / type 筛选"""
    db = get_db()
    tag_list = tags.split(",") if tags else None
    assets, total = await db.list_assets(
        source=source, tags=tag_list, favorite=favorite,
        group_id=group_id, type=type, limit=limit, offset=offset,
    )
    items = [await _asset_to_response(a) for a in assets]
    return AssetListResponse(items=items, total=total)


@router.post("/assets", response_model=AssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    tags: str = Form(""),
    parent_id: str | None = Form(None),
    group_id: str | None = Form(None),
):
    """上传素材（走 Ingest Pipeline → COS）

    支持图片（image/*）、视频（video/*）、音频（audio/*）和文本（text/plain）。
    """
    db = get_db()
    storage = get_storage()

    data = await file.read()
    tag_list = tags.split(",") if tags else []
    content_type = file.content_type or ""

    pipeline = IngestPipeline(storage, db)

    # 根据 Content-Type 分发到不同的 ingest 方法
    if content_type.startswith("text/plain"):
        content = data.decode("utf-8")
        asset = await pipeline.ingest_text(
            content=content,
            filename=file.filename or "",
            source="uploaded",
            tags=tag_list,
            parent_id=parent_id,
            group_id=group_id,
        )
    elif content_type.startswith("audio/"):
        asset = await pipeline.ingest_audio(
            data=data,
            filename=file.filename or "",
            source="uploaded",
            tags=tag_list,
            parent_id=parent_id,
            group_id=group_id,
        )
    else:
        asset = await pipeline.ingest(
            data=data,
            filename=file.filename or "",
            source="uploaded",
            tags=tag_list,
            parent_id=parent_id,
            group_id=group_id,
        )

    return await _asset_to_response(asset)


@router.put("/assets/{asset_id}/content", response_model=AssetResponse)
async def replace_asset_content(
    asset_id: str,
    file: UploadFile = File(...),
):
    """覆盖原素材内容（id/parent_id/tags/favorite 保留）。

    用于素材编辑器的"覆盖原图"操作。前端把编辑后的 PNG 用 multipart 上传即可。
    """
    db = get_db()
    storage = get_storage()

    existing = await db.get_asset(asset_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")

    data = await file.read()
    pipeline = IngestPipeline(storage, db)
    asset = await pipeline.replace(asset_id, data)
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
    storage = get_storage()
    asset = await db.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")
    # 同步删除 COS 对象存储中的文件
    for uri in (asset.uri, asset.thumbnail):
        if not uri:
            continue
        try:
            await storage.delete(uri)
        except Exception:
            pass
    success = await db.delete_asset(asset_id)
    return {"status": "deleted"}


# ---------------- 批量操作 ----------------


class BatchDeleteRequest(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1)


class BatchMoveRequest(BaseModel):
    asset_ids: list[str] = Field(..., min_length=1)
    group_id: str | None = None  # None = 移出分组


@router.post("/assets/batch-delete")
async def batch_delete(req: BatchDeleteRequest):
    """批量删除素材"""
    db = get_db()
    storage = get_storage()
    # 先查出所有素材的 COS URI
    assets_to_delete: list[Asset] = []
    for asset_id in req.asset_ids:
        asset = await db.get_asset(asset_id)
        if asset:
            assets_to_delete.append(asset)
    # 同步删除 COS 对象存储中的文件
    for asset in assets_to_delete:
        for uri in (asset.uri, asset.thumbnail):
            if not uri:
                continue
            try:
                await storage.delete(uri)
            except Exception:
                pass
    count = await db.batch_delete_assets(req.asset_ids)
    return {"status": "deleted", "count": count}


@router.post("/assets/batch-move")
async def batch_move(req: BatchMoveRequest):
    """批量移动素材到分组"""
    db = get_db()
    count = await db.move_assets_to_group(req.asset_ids, req.group_id)
    return {"status": "moved", "count": count}


@router.put("/assets/{asset_id}/group")
async def set_asset_group(asset_id: str, group_id: str | None = Query(None)):
    """设置单个素材的分组"""
    db = get_db()
    count = await db.move_assets_to_group([asset_id], group_id)
    if not count:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")
    return {"status": "moved"}


# ---------------- 分组 CRUD ----------------


@router.get("/groups", response_model=GroupListResponse)
async def list_groups():
    db = get_db()
    groups = await db.list_groups()
    return GroupListResponse(items=[
        GroupResponse(id=g.id, name=g.name, description=g.description, created_at=g.created_at)
        for g in groups
    ])


@router.post("/groups", response_model=GroupResponse)
async def create_group(
    name: str = Form(...),
    description: str = Form(""),
):
    from ..asset_hub.models import AssetGroup
    db = get_db()
    group = AssetGroup(name=name, description=description)
    await db.create_group(group)
    return GroupResponse(id=group.id, name=group.name, description=group.description, created_at=group.created_at)


@router.put("/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    name: str | None = Form(None),
    description: str | None = Form(None),
):
    db = get_db()
    ok = await db.update_group(group_id, name=name, description=description)
    if not ok:
        raise HTTPException(status_code=404, detail=f"分组不存在: {group_id}")
    g = await db.get_group(group_id)
    assert g is not None
    return GroupResponse(id=g.id, name=g.name, description=g.description, created_at=g.created_at)


@router.delete("/groups/{group_id}")
async def delete_group(group_id: str):
    db = get_db()
    success = await db.delete_group(group_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"分组不存在: {group_id}")
    return {"status": "deleted"}


# ---------------- 图片代理 ----------------
_ALLOWED_PROXY_HOSTS = (
    ".myqcloud.com",
    ".cos.tencentcs.com",
    ".tencentyun.com",
)


def _is_url_allowed(url: str) -> bool:
    """只允许代理白名单内的图片源，避免 SSRF。"""
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
        if not host:
            return False
        return any(host.endswith(suffix) for suffix in _ALLOWED_PROXY_HOSTS)
    except Exception:
        return False


@router.get("/assets/{asset_id}/raw")
async def proxy_asset_raw(asset_id: str, thumb: bool = Query(False)):
    """通过 asset_id 同源拉取原图/缩略图（自动签名 + 流式回吐）。"""
    db = get_db()
    storage = get_storage()
    asset = await db.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")

    # 本地存储：直接读取文件
    from ..storage.local_storage import LocalStorage
    if isinstance(storage, LocalStorage):
        target_uri = (asset.thumbnail if thumb and asset.thumbnail else asset.uri)
        path = storage._uri_to_path(target_uri)
        if not path.exists():
            raise HTTPException(status_code=404, detail="文件不存在")
        media_type = "image/png" if path.suffix == ".png" else "image/jpeg"
        return FileResponse(path, media_type=media_type)

    # COS 存储：生成预签名 URL 并代理
    target_uri = asset.thumbnail if thumb and asset.thumbnail else asset.uri
    try:
        url = await storage.get_presigned_url(target_uri, expires=600)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"签名失败: {e}") from e

    return await _stream_proxy(url)


@router.get("/proxy-image")
async def proxy_image(url: str = Query(..., description="远端图片 URL（仅限白名单域名）")):
    """通用图片代理：把任意白名单内的远端图片以同源方式回吐给浏览器。"""
    if not _is_url_allowed(url):
        raise HTTPException(status_code=400, detail="代理目标不在允许列表内")
    return await _stream_proxy(url)


async def _stream_proxy(url: str) -> StreamingResponse:
    """从远端拉图，流式透传给客户端，并附带 CORS 友好的响应头。"""
    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    try:
        upstream = await client.send(
            client.build_request("GET", url), stream=True
        )
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"上游获取失败: {e}") from e

    if upstream.status_code >= 400:
        body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=upstream.status_code,
            detail=f"上游返回 {upstream.status_code}: {body[:200].decode('utf-8', 'ignore')}",
        )

    media_type = upstream.headers.get("content-type", "application/octet-stream")

    async def iterator():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        iterator(),
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Access-Control-Allow-Origin": "*",
        },
    )
