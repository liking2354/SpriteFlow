"""创作任务 API — 持久化的生成记录"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..asset_hub.models import GenerationJob, Asset
from .deps import get_db, get_storage

router = APIRouter()


class ChildPlaceholder(BaseModel):
    """父卡内待显示的"再次生成"占位/子任务"""
    job_id: str
    status: str
    error: str | None = None
    created_at: str


class JobResponse(BaseModel):
    id: str
    mode: str
    prompt: str
    params: dict
    ref_image_urls: list[str]
    ref_asset_ids: list[str]
    asset_ids: list[str]
    status: str
    error: str | None = None
    favorite: bool
    model: str | None = None
    usage: dict | None = None
    parent_id: str | None = None
    created_at: str
    finished_at: str | None = None
    # 输出图（自身 + 所有 children 的，按时间顺序）
    assets: list[dict] = []
    # 参考图
    ref_assets: list[dict] = []
    # 仍在进行的子任务（用于占位卡）
    pending_children: list[ChildPlaceholder] = []


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


async def _resolve_assets(asset_ids: list[str]) -> list[dict]:
    if not asset_ids:
        return []
    db = get_db()
    storage = get_storage()
    assets = await db.get_assets_by_ids(asset_ids)
    out: list[dict] = []
    for a in assets:
        url = a.uri
        thumb = a.thumbnail
        try:
            url = await storage.get_presigned_url(a.uri, expires=86400)
            if a.thumbnail:
                thumb = await storage.get_presigned_url(a.thumbnail, expires=86400)
        except Exception:
            pass
        out.append({
            "id": a.id,
            "url": url,
            "thumbnail": thumb,
            "width": a.width,
            "height": a.height,
            "favorite": a.favorite,
            "tags": a.tags,
        })
    return out


async def _resolve_refs(job: GenerationJob) -> list[dict]:
    db = get_db()
    storage = get_storage()
    refs: list[dict] = []
    if job.ref_asset_ids:
        ref_assets = await db.get_assets_by_ids(job.ref_asset_ids)
        for a in ref_assets:
            url = a.uri
            thumb = a.thumbnail
            try:
                url = await storage.get_presigned_url(a.uri, expires=86400)
                if a.thumbnail:
                    thumb = await storage.get_presigned_url(a.thumbnail, expires=86400)
            except Exception:
                pass
            refs.append({
                "asset_id": a.id,
                "url": url,
                "thumbnail": thumb,
                "width": a.width,
                "height": a.height,
                "origin": "asset",
            })
    for u in job.ref_image_urls or []:
        refs.append({
            "asset_id": None,
            "url": u,
            "thumbnail": u,
            "origin": "url",
        })
    return refs


async def _job_to_response(job: GenerationJob) -> JobResponse:
    db = get_db()

    # 自身资产
    own_assets = await _resolve_assets(job.asset_ids)

    # 子任务（再次生成产物）—— 把它们的资产追加到父 assets，运行中的子作为占位
    children = await db.list_children_jobs(job.id)
    pending: list[ChildPlaceholder] = []
    child_assets: list[dict] = []
    for c in children:
        if c.status in ("pending", "running"):
            pending.append(ChildPlaceholder(
                job_id=c.id,
                status=c.status,
                error=c.error,
                created_at=c.created_at,
            ))
        elif c.status == "failed":
            pending.append(ChildPlaceholder(
                job_id=c.id,
                status="failed",
                error=c.error,
                created_at=c.created_at,
            ))
        else:
            child_assets.extend(await _resolve_assets(c.asset_ids))

    return JobResponse(
        id=job.id,
        mode=job.mode,
        prompt=job.prompt,
        params=job.params,
        ref_image_urls=job.ref_image_urls,
        ref_asset_ids=job.ref_asset_ids,
        asset_ids=job.asset_ids,
        status=job.status,
        error=job.error,
        favorite=job.favorite,
        model=job.model,
        usage=job.usage,
        parent_id=job.parent_id,
        created_at=job.created_at,
        finished_at=job.finished_at,
        assets=own_assets + child_assets,
        ref_assets=await _resolve_refs(job),
        pending_children=pending,
    )


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    favorite: bool | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """查询创作记录列表（仅顶层任务，再次生成的子任务合并显示在父卡内）"""
    db = get_db()
    jobs, total = await db.list_jobs(
        favorite=favorite, limit=limit, offset=offset, only_root=True,
    )
    items = [await _job_to_response(j) for j in jobs]
    return JobListResponse(items=items, total=total)


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    db = get_db()
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return await _job_to_response(job)


@router.put("/jobs/{job_id}/favorite")
async def set_job_favorite(job_id: str, body: dict):
    db = get_db()
    favorite = bool(body.get("favorite", True))
    success = await db.set_job_favorite(job_id, favorite)
    if not success:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return {"status": "ok", "favorite": favorite}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    db = get_db()
    # 同时删除所有子任务
    children = await db.list_children_jobs(job_id)
    for c in children:
        await db.delete_job(c.id)
    success = await db.delete_job(job_id)
    if not success:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return {"status": "deleted"}


@router.post("/jobs/{job_id}/regenerate", response_model=JobResponse)
async def regenerate_job(job_id: str):
    """再次生成 —— 用原任务参数克隆并启动一个新任务，关联为子任务"""
    from .generate import (
        _MODE_TO_CAP,
        _validate_refs,
        _build_payload,
        _persist_image,
        get_router as _get_router,
    )
    from ..providers.base import Capability  # noqa: F401

    db = get_db()
    parent = await db.get_job(job_id)
    if not parent:
        raise HTTPException(404, f"任务不存在: {job_id}")

    cap = _MODE_TO_CAP.get(parent.mode)
    if cap is None:
        raise HTTPException(400, f"父任务的 mode 不支持: {parent.mode}")

    # 找根（如果父任务自己也是 child，挂到同一根）
    root_id = parent.parent_id or parent.id

    # 克隆参数
    new_job = GenerationJob(
        mode=parent.mode,
        prompt=parent.prompt,
        params=parent.params,
        ref_image_urls=parent.ref_image_urls,
        ref_asset_ids=parent.ref_asset_ids,
        parent_id=root_id,
        status="running",
    )
    await db.create_job(new_job)

    # 后台执行
    async def _runner() -> None:
        try:
            # 复用 generate.py 的 _resolve_refs：但它依赖请求对象。这里直接展开。
            from .generate import _resolve_refs as _resolve_req_refs, GenerateRequest

            req = GenerateRequest(
                mode=parent.mode,
                prompt=parent.prompt,
                image_urls=parent.ref_image_urls,
                ref_asset_ids=parent.ref_asset_ids,
                size=str(parent.params.get("size", "2k")),
                width=parent.params.get("width"),
                height=parent.params.get("height"),
                seed=parent.params.get("seed"),
                max_images=int(parent.params.get("max_images") or 1),
                web_search=bool(parent.params.get("web_search", False)),
                watermark=bool(parent.params.get("watermark", False)),
                save_as_asset=True,
                tags=list(parent.params.get("tags") or []),
            )
            refs = await _resolve_req_refs(req)
            _validate_refs(parent.mode, refs)

            router_inst = _get_router()
            payload = _build_payload(cap, req, refs)
            result = await router_inst.route(cap, payload)

            images = result.get("images") or (
                [result["image"]] if result.get("image") else []
            )
            if not images:
                await db.update_job(
                    new_job.id, status="failed", error="provider 未返回图片",
                    finished_at=datetime.now().isoformat(),
                )
                return

            asset_ids: list[str] = []
            for idx, img in enumerate(images):
                tags = list(parent.params.get("tags") or []) + [
                    f"mode:{parent.mode}", "regen"
                ]
                if parent.mode == "sequential" and len(images) > 1:
                    tags.append(f"seq:{idx}")
                info = await _persist_image(img, parent.prompt, tags)
                if info.get("asset_id"):
                    asset_ids.append(info["asset_id"])

            await db.update_job(
                new_job.id,
                status="completed",
                asset_ids=asset_ids,
                model=result.get("model"),
                usage=result.get("usage", {}),
                finished_at=datetime.now().isoformat(),
            )
        except HTTPException as e:
            await db.update_job(
                new_job.id, status="failed", error=str(e.detail),
                finished_at=datetime.now().isoformat(),
            )
        except Exception as e:
            await db.update_job(
                new_job.id, status="failed", error=str(e),
                finished_at=datetime.now().isoformat(),
            )

    asyncio.create_task(_runner())

    # 返回根任务最新状态（带 pending_children）
    root = await db.get_job(root_id)
    if not root:
        raise HTTPException(500, "根任务丢失")
    return await _job_to_response(root)


@router.put("/assets/{asset_id}/favorite")
async def set_asset_favorite(asset_id: str, body: dict):
    db = get_db()
    favorite = bool(body.get("favorite", True))
    success = await db.set_asset_favorite(asset_id, favorite)
    if not success:
        raise HTTPException(404, f"素材不存在: {asset_id}")
    return {"status": "ok", "favorite": favorite}
