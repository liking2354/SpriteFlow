"""快捷生图 API — 不依赖 YAML，前端直接表单调用

涵盖 4 种 Seedream 能力：text2img / img2img / multi_fusion / sequential
所有调用都会持久化为 GenerationJob 任务记录。
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..asset_hub.models import GenerationJob
from ..providers.base import Capability
from .deps import get_router, get_storage, get_db
from ..asset_hub.ingest import IngestPipeline

router = APIRouter()


# ============================ 请求模型 ============================


class GenerateRequest(BaseModel):
    """统一的快捷生图请求"""

    mode: str = Field(..., description="text2img | img2img | multi_fusion | sequential")
    prompt: str = Field(..., description="提示词")
    image_urls: list[str] = Field(default_factory=list)
    ref_asset_ids: list[str] = Field(default_factory=list, description="素材库内参考图 id")
    size: str = Field("2K", description="2K / 4K / 自定义如 2048x2048 / adaptive")
    width: int | None = None             # 自定义宽（与 height 配对，覆盖 size）
    height: int | None = None
    seed: int | None = None
    max_images: int = Field(1, ge=1, le=15)
    web_search: bool = False
    watermark: bool = False
    save_as_asset: bool = True
    tags: list[str] = Field(default_factory=list)
    group_id: str | None = None


class GeneratedImage(BaseModel):
    url: str
    asset_id: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail: str | None = None
    favorite: bool = False


class GenerateResponse(BaseModel):
    job_id: str
    images: list[GeneratedImage]
    usage: dict[str, Any] = {}
    model: str | None = None


# ============================ 流式 bus ============================


_run_buses: dict[str, asyncio.Queue] = {}


def register_run(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    _run_buses[run_id] = q
    return q


def get_run_bus(run_id: str) -> asyncio.Queue | None:
    return _run_buses.get(run_id)


async def push_event(run_id: str, event: dict[str, Any]) -> None:
    q = _run_buses.get(run_id)
    if q is not None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def close_run(run_id: str) -> None:
    q = _run_buses.pop(run_id, None)
    if q is not None:
        try:
            q.put_nowait({"type": "done"})
        except asyncio.QueueFull:
            pass


# ============================ 工具方法 ============================


_MODE_TO_CAP = {
    "text2img": Capability.TEXT2IMG,
    "img2img": Capability.IMG2IMG,
    "multi_fusion": Capability.MULTI_IMAGE_FUSION,
    "sequential": Capability.SEQUENTIAL_IMAGES,
}


def _resolve_size(req: GenerateRequest) -> str:
    """优先取 width×height，否则用 size 字符串"""
    if req.width and req.height:
        return f"{int(req.width)}x{int(req.height)}"
    return req.size or "2K"


async def _resolve_refs(req: GenerateRequest) -> list[str]:
    """合并 image_urls + 素材库 ref_asset_ids（转成预签名 URL）"""
    refs: list[str] = list(req.image_urls or [])
    if req.ref_asset_ids:
        db = get_db()
        storage = get_storage()
        assets = await db.get_assets_by_ids(req.ref_asset_ids)
        for a in assets:
            try:
                url = await storage.get_presigned_url(a.uri, expires=3600)
                refs.append(url)
            except Exception:
                refs.append(a.uri)
    return refs


def _build_payload(
    cap: Capability,
    req: GenerateRequest,
    refs: list[str],
    run_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": req.prompt,
        "size": _resolve_size(req),
        "seed": req.seed,
        "watermark": req.watermark,
        "output_format": "png",
        "response_format": "url",
        "web_search": req.web_search,
    }
    if cap == Capability.IMG2IMG:
        if not refs:
            raise HTTPException(400, "img2img 需要至少 1 张参考图")
        payload["image"] = refs[0]
    elif cap == Capability.MULTI_IMAGE_FUSION:
        if len(refs) < 2:
            raise HTTPException(400, "multi_fusion 需要至少 2 张参考图")
        payload["image"] = refs
    elif cap == Capability.SEQUENTIAL_IMAGES:
        if refs:
            payload["image"] = refs if len(refs) > 1 else refs[0]
        payload["max_images"] = req.max_images
        payload["stream"] = bool(run_id)
        if run_id:
            async def _on_event(evt: dict) -> None:
                await push_event(run_id, evt)
            payload["on_event"] = _on_event
    return payload


async def _persist_image(image, prompt: str, tags: list[str], group_id: str | None = None) -> dict[str, Any]:
    storage = get_storage()
    db = get_db()
    pipeline = IngestPipeline(storage, db)

    buf = io.BytesIO()
    image.convert("RGBA").save(buf, format="PNG")
    raw = buf.getvalue()

    asset = await pipeline.ingest(
        data=raw,
        filename=f"seedream_{uuid.uuid4().hex[:12]}.png",
        source="generated",
        tags=tags,
        group_id=group_id,
        provenance={"prompt": prompt, "generated_at": datetime.now().isoformat()},
    )
    presigned = await storage.get_presigned_url(asset.uri, expires=86400)
    thumb = (
        await storage.get_presigned_url(asset.thumbnail, expires=86400)
        if asset.thumbnail else None
    )
    return {
        "url": presigned,
        "asset_id": asset.id,
        "width": asset.width,
        "height": asset.height,
        "thumbnail": thumb,
        "favorite": asset.favorite,
    }


def _make_job_record(req: GenerateRequest) -> GenerationJob:
    return GenerationJob(
        mode=req.mode,
        prompt=req.prompt,
        params={
            "size": _resolve_size(req),
            "width": req.width,
            "height": req.height,
            "seed": req.seed,
            "max_images": req.max_images,
            "web_search": req.web_search,
            "watermark": req.watermark,
            "tags": req.tags,
        },
        ref_image_urls=req.image_urls or [],
        ref_asset_ids=req.ref_asset_ids or [],
        status="running",
    )


# ============================ 端点 ============================


def _validate_refs(mode: str, refs: list[str]) -> None:
    """按模式校验参考图数量"""
    if mode == "img2img" and not refs:
        raise HTTPException(400, "img2img 需要至少 1 张参考图")
    if mode == "multi_fusion" and len(refs) < 2:
        raise HTTPException(400, "multi_fusion 需要至少 2 张参考图")


@router.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    """快捷生图（异步执行）

    立即创建 GenerationJob 记录并返回 job_id，真正的生图在后台 task 完成。
    前端通过轮询 /api/jobs 拿到状态从 running → completed 的更新。

    严格按模式对应能力调用：仅 sequential 模式支持多张（max_images），
    其余模式（text2img/img2img/multi_fusion）按接口语义产出单图。
    """
    cap = _MODE_TO_CAP.get(req.mode)
    if cap is None:
        raise HTTPException(400, f"不支持的 mode: {req.mode}")

    # 同步阶段：参数校验 + 创建 job 记录
    db = get_db()
    job = _make_job_record(req)
    await db.create_job(job)

    # 后台异步执行
    async def _runner() -> None:
        try:
            refs = await _resolve_refs(req)
            _validate_refs(req.mode, refs)
            router_inst = get_router()
            payload = _build_payload(cap, req, refs)
            result = await router_inst.route(cap, payload)

            images = result.get("images") or (
                [result["image"]] if result.get("image") else []
            )
            if not images:
                await db.update_job(
                    job.id, status="failed", error="provider 未返回图片",
                    finished_at=datetime.now().isoformat(),
                )
                return

            asset_ids: list[str] = []
            for idx, img in enumerate(images):
                if not req.save_as_asset:
                    continue
                tags = list(req.tags) + [f"mode:{req.mode}"]
                if req.mode == "sequential" and len(images) > 1:
                    tags.append(f"seq:{idx}")
                info = await _persist_image(img, req.prompt, tags, req.group_id)
                if info.get("asset_id"):
                    asset_ids.append(info["asset_id"])

            await db.update_job(
                job.id,
                status="completed",
                asset_ids=asset_ids,
                model=result.get("model"),
                usage=result.get("usage", {}),
                finished_at=datetime.now().isoformat(),
            )
        except HTTPException as e:
            await db.update_job(
                job.id, status="failed", error=e.detail or "invalid request",
                finished_at=datetime.now().isoformat(),
            )
        except Exception as e:
            await db.update_job(
                job.id, status="failed", error=str(e),
                finished_at=datetime.now().isoformat(),
            )

    asyncio.create_task(_runner())

    # 立即返回（任务尚未完成，前端凭 job_id 轮询）
    return GenerateResponse(
        job_id=job.id,
        images=[],
        usage={},
        model=None,
    )


@router.post("/generate/stream/start")
async def stream_generate_start(req: GenerateRequest):
    """启动流式 sequential 生成；返回 run_id（也是 job_id）

    前端用 GET /api/generate/stream/{run_id} 订阅 SSE
    """
    if req.mode != "sequential":
        raise HTTPException(400, "stream 仅支持 sequential 模式")

    cap = Capability.SEQUENTIAL_IMAGES
    db = get_db()
    job = _make_job_record(req)
    await db.create_job(job)

    register_run(job.id)
    router_inst = get_router()

    async def _runner() -> None:
        try:
            await push_event(job.id, {"type": "started", "run_id": job.id, "job_id": job.id})
            refs = await _resolve_refs(req)
            payload = _build_payload(cap, req, refs, run_id=job.id)
            result = await router_inst.route(cap, payload)

            images = result.get("images") or []
            persisted: list[dict[str, Any]] = []
            asset_ids: list[str] = []

            if req.save_as_asset:
                for idx, img in enumerate(images):
                    tags = list(req.tags) + ["mode:sequential", f"seq:{idx}"]
                    info = await _persist_image(img, req.prompt, tags, req.group_id)
                    persisted.append(info)
                    if info.get("asset_id"):
                        asset_ids.append(info["asset_id"])
                    await push_event(job.id, {
                        "type": "image_persisted",
                        "index": idx,
                        **info,
                    })

            await db.update_job(
                job.id,
                status="completed",
                asset_ids=asset_ids,
                model=result.get("model"),
                usage=result.get("usage", {}),
                finished_at=datetime.now().isoformat(),
            )

            await push_event(job.id, {
                "type": "completed",
                "job_id": job.id,
                "images": persisted,
                "usage": result.get("usage", {}),
                "model": result.get("model"),
            })
        except Exception as e:
            await db.update_job(
                job.id, status="failed", error=str(e),
                finished_at=datetime.now().isoformat(),
            )
            await push_event(job.id, {"type": "error", "message": str(e), "job_id": job.id})
        finally:
            close_run(job.id)

    asyncio.create_task(_runner())
    return {"run_id": job.id, "job_id": job.id}


@router.get("/generate/stream/{run_id}")
async def stream_generate_events(run_id: str):
    q = get_run_bus(run_id)
    if q is None:
        raise HTTPException(404, f"run 不存在或已结束: {run_id}")

    async def _iter() -> AsyncIterator[dict[str, str]]:
        while True:
            evt = await q.get()
            yield {"data": json.dumps(evt, ensure_ascii=False)}
            if evt.get("type") in ("done", "completed", "error"):
                break

    return EventSourceResponse(_iter())
