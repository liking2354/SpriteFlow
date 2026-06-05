"""素材 API — 上传、查询、详情+血缘

所有响应中的 uri/thumbnail 都返回为 COS 预签名 URL（24h 有效），
方便前端直接用于 <img src=...>；底层 cos:// 路径不暴露给前端。
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import StreamingResponse
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
        group_id=asset.group_id,
        provenance=asset.provenance,
        favorite=asset.favorite,
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
    success = await db.delete_asset(asset_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")
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
# 用途：前端 Canvas 编辑器（filerobot / 抠图）需要把图片读成 blob。
# 部分 COS 域名未开放 CORS 时会触发 "TypeError: Failed to fetch"，
# 这里提供同源代理通道，浏览器侧只需请求 /api/proxy-image/...
# 即可绕过跨域限制。
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
async def proxy_asset_raw(asset_id: str):
    """通过 asset_id 同源拉取原图（自动签名 + 流式回吐）。"""
    db = get_db()
    storage = get_storage()
    asset = await db.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"素材不存在: {asset_id}")

    try:
        url = await storage.get_presigned_url(asset.uri, expires=600)
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


# ---------------- AI 图像处理 ----------------


class AIProcessRequest(BaseModel):
    """AI 图像处理请求体"""

    asset_id: str = Field(..., description="源素材 ID")
    capability: str = Field(
        ...,
        description="处理能力: enhance_photo / image_inpaint / remove_bg / image_cut / image_outpaint / slim_image / resize_image",
    )
    group_id: str | None = None
    # 各能力可选参数
    req_key: str | None = None
    width: int | None = None
    height: int | None = None
    cut_method: str | None = None
    resize_long: int | None = None
    resize_short: int | None = None
    resize_mode: str | None = None
    output_format: str | None = None
    scale: float | None = None
    refine: str | None = None


@router.post("/assets/ai-process")
async def ai_process(req: AIProcessRequest):
    """调用火山引擎 AI 图像处理，结果保存为新素材并返回"""
    from ..providers.base import Capability, Credential
    from .deps import get_router

    router = get_router()

    # 映射 capability 字符串到枚举
    cap_map = {
        "enhance_photo": Capability.ENHANCE_PHOTO,
        "image_inpaint": Capability.IMAGE_INPAINT,
        "remove_bg": Capability.REMOVE_BG,
        "image_cut": Capability.IMAGE_CUT,
        "image_outpaint": Capability.IMAGE_OUTPAINT,
        "slim_image": Capability.SLIM_IMAGE,
        "resize_image": Capability.RESIZE_IMAGE,
    }
    cap = cap_map.get(req.capability)
    if not cap:
        raise HTTPException(status_code=400, detail=f"不支持的 capability: {req.capability}")

    # 获取源素材
    db = get_db()
    storage = get_storage()
    asset = await db.get_asset(req.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"素材不存在: {req.asset_id}")

    # 下载源图片 bytes
    try:
        url = await storage.get_presigned_url(asset.uri, expires=600)
    except Exception:
        url = asset.uri

    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        image_bytes = resp.content

    # 构造 payload
    payload: dict = {"image_bytes": image_bytes}
    if req.req_key:
        payload["req_key"] = req.req_key
    if req.width is not None:
        payload["width"] = req.width
    if req.height is not None:
        payload["height"] = req.height
    if req.cut_method:
        payload["cut_method"] = req.cut_method
    if req.resize_long is not None:
        payload["resize_long"] = req.resize_long
    if req.resize_short is not None:
        payload["resize_short"] = req.resize_short
    if req.resize_mode:
        payload["resize_mode"] = req.resize_mode
    if req.output_format:
        payload["output_format"] = req.output_format
    if req.scale is not None:
        payload["scale"] = req.scale
    if req.refine:
        payload["refine"] = req.refine

    # 调用 provider
    cred = Credential(provider_name="volcengine_image")
    try:
        result = await router.route(cap, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 处理失败: {e}") from e

    # 保存结果到素材库（兼容两种结果格式）
    import io
    result_bytes = result.get("image_bytes")
    if result_bytes is None:
        # rembg provider 返回 PIL.Image 对象
        result_image = result.get("image")
        if result_image is not None:
            buf = io.BytesIO()
            result_image.save(buf, format="PNG")
            result_bytes = buf.getvalue()

    if not result_bytes:
        raise HTTPException(status_code=500, detail="AI 处理未返回图片数据")

    pipeline = IngestPipeline(storage, db)
    new_asset = await pipeline.ingest(
        data=result_bytes,
        filename=f"{req.capability}_{asset.id}.png",
        source="ai_processed",
        tags=[req.capability],
        parent_id=req.asset_id,
        group_id=req.group_id,
    )

    return await _asset_to_response(new_asset)
