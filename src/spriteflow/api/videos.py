"""视频生成任务 API

转发火山方舟 Seedance 2.0 视频生成接口，并把任务状态/结果存入本地 video_tasks 表。
worker 在后台轮询完成态并把视频下载入库（type=video 的 Asset，目录 videos/）。

路径前缀：/api
  POST   /api/videos/tasks                 创建任务
  GET    /api/videos/tasks                 列表（本地分页 + 可选 status 过滤）
  GET    /api/videos/tasks/{id}            查询单任务（带 input/output asset 详情）
  POST   /api/videos/tasks/{id}/cancel     取消任务（仅 queued）
  DELETE /api/videos/tasks/{id}            删除任务（结束态/失败/已取消）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .deps import get_db, get_storage
from .assets import _asset_to_response, AssetResponse  # noqa: WPS450 — 复用工具
from ..asset_hub.video_models import VideoTask
from ..providers.seedance import SeedanceProvider
from ..config import settings

router = APIRouter()


# ============================ Schemas ============================


class VideoCreateInput(BaseModel):
    """前端创建任务的载荷（结构化字段，由后端组装 Seedance content 数组）"""

    mode: Literal["text2video", "image2video_first", "first_last", "multi_ref"]
    prompt: str = ""
    # 输入素材（asset_id），后端转成 COS 预签名 URL 后塞 content 数组
    first_frame_asset_id: str | None = None
    last_frame_asset_id: str | None = None
    ref_asset_ids: list[str] = Field(default_factory=list)
    # 公共可选参数
    model: str | None = None
    ratio: str | None = None              # 16:9 / 4:3 / 1:1 / 3:4 / 9:16 / 21:9 / adaptive
    resolution: str | None = None         # 480p / 720p
    duration: int | None = None           # 4~15
    seed: int | None = None
    camerafixed: bool | None = None
    watermark: bool | None = None
    return_last_frame: bool | None = None
    generate_audio: bool | None = None
    execution_expires_after: int | None = None


class VideoTaskOut(BaseModel):
    id: str
    provider: str
    provider_task_id: str | None
    model: str
    mode: str
    prompt: str
    params: dict[str, Any]
    status: str
    error: str | None
    result_asset: AssetResponse | None
    last_frame_asset: AssetResponse | None
    inputs: dict[str, Any]
    usage_tokens: int | None
    created_at: str
    updated_at: str
    completed_at: str | None


class VideoListOut(BaseModel):
    items: list[VideoTaskOut]
    total: int
    limit: int
    offset: int


# ============================ Helpers ============================


def _seedance() -> SeedanceProvider:
    return SeedanceProvider(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
        model=settings.seedance_model,
        timeout=settings.seedance_request_timeout,
    )


async def _to_out(t: VideoTask) -> VideoTaskOut:
    db = get_db()
    res_asset_resp: AssetResponse | None = None
    last_asset_resp: AssetResponse | None = None
    if t.result_asset_id:
        a = await db.get_asset(t.result_asset_id)
        if a:
            res_asset_resp = await _asset_to_response(a)
    if t.last_frame_asset_id:
        a = await db.get_asset(t.last_frame_asset_id)
        if a:
            last_asset_resp = await _asset_to_response(a)
    return VideoTaskOut(
        id=t.id,
        provider=t.provider,
        provider_task_id=t.provider_task_id,
        model=t.model,
        mode=t.mode,
        prompt=t.prompt,
        params=t.params,
        status=t.status,
        error=t.error,
        result_asset=res_asset_resp,
        last_frame_asset=last_asset_resp,
        inputs=t.inputs,
        usage_tokens=t.usage_tokens,
        created_at=t.created_at,
        updated_at=t.updated_at,
        completed_at=t.completed_at,
    )


async def _build_content(payload: VideoCreateInput) -> list[dict[str, Any]]:
    """把前端的 mode + asset_ids 组装成 Seedance content[] 数组。

    asset 走 COS 预签名 URL（1 小时有效，足够任务排队启动）。
    """
    storage = get_storage()
    db = get_db()
    content: list[dict[str, Any]] = []

    if payload.prompt:
        content.append({"type": "text", "text": payload.prompt})

    async def _asset_url(asset_id: str) -> str:
        a = await db.get_asset(asset_id)
        if not a:
            raise HTTPException(status_code=400, detail=f"素材不存在: {asset_id}")
        try:
            return await storage.get_presigned_url(a.uri, expires=3600)
        except Exception:
            return a.uri  # 退回原 URI（本地存储等）

    if payload.mode == "image2video_first":
        if not payload.first_frame_asset_id:
            raise HTTPException(status_code=400, detail="image2video_first 需要 first_frame_asset_id")
        url = await _asset_url(payload.first_frame_asset_id)
        content.append({
            "type": "image_url", "image_url": {"url": url}, "role": "first_frame",
        })
    elif payload.mode == "first_last":
        if not (payload.first_frame_asset_id and payload.last_frame_asset_id):
            raise HTTPException(status_code=400, detail="first_last 需要同时提供 first 与 last")
        u1 = await _asset_url(payload.first_frame_asset_id)
        u2 = await _asset_url(payload.last_frame_asset_id)
        content.append({"type": "image_url", "image_url": {"url": u1}, "role": "first_frame"})
        content.append({"type": "image_url", "image_url": {"url": u2}, "role": "last_frame"})
    elif payload.mode == "multi_ref":
        if not payload.ref_asset_ids:
            raise HTTPException(status_code=400, detail="multi_ref 至少 1 张参考图")
        if len(payload.ref_asset_ids) > 9:
            raise HTTPException(status_code=400, detail="参考图最多 9 张")
        for aid in payload.ref_asset_ids:
            url = await _asset_url(aid)
            content.append({
                "type": "image_url", "image_url": {"url": url}, "role": "reference_image",
            })
    elif payload.mode == "text2video":
        if not payload.prompt:
            raise HTTPException(status_code=400, detail="text2video 需要 prompt")
    else:
        raise HTTPException(status_code=400, detail=f"未知 mode: {payload.mode}")

    return content


def _collect_optional_params(p: VideoCreateInput) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for k in (
        "ratio", "resolution", "duration", "seed", "camerafixed",
        "watermark", "return_last_frame", "generate_audio", "execution_expires_after",
    ):
        v = getattr(p, k)
        if v is not None:
            body[k] = v
    return body


# ============================ Routes ============================


@router.post("/videos/tasks", response_model=VideoTaskOut)
async def create_video_task(payload: VideoCreateInput) -> VideoTaskOut:
    if not settings.ark_api_key:
        raise HTTPException(status_code=400, detail="ARK_API_KEY 未配置")

    db = get_db()
    seedance = _seedance()

    content = await _build_content(payload)
    body: dict[str, Any] = {
        "model": payload.model or settings.seedance_model,
        "content": content,
        **_collect_optional_params(payload),
    }

    try:
        resp = await seedance.create_task(body, api_key=settings.ark_api_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"创建任务失败: {e}") from e

    provider_task_id = resp.get("id") or resp.get("task_id")
    if not provider_task_id:
        raise HTTPException(status_code=502, detail=f"远端未返回 task id: {resp}")

    now = datetime.now().isoformat()
    task = VideoTask(
        provider="seedance",
        provider_task_id=str(provider_task_id),
        model=body["model"],
        mode=payload.mode,
        prompt=payload.prompt,
        params=_collect_optional_params(payload),
        inputs={
            "first_frame_asset_id": payload.first_frame_asset_id,
            "last_frame_asset_id": payload.last_frame_asset_id,
            "ref_asset_ids": payload.ref_asset_ids,
        },
        status="queued",
        created_at=now,
        updated_at=now,
    )
    await db.create_video_task(task)
    return await _to_out(task)


@router.get("/videos/tasks", response_model=VideoListOut)
async def list_video_tasks(
    status: str | None = Query(None, description="可选状态过滤"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> VideoListOut:
    db = get_db()
    items, total = await db.list_video_tasks(status=status, limit=limit, offset=offset)
    return VideoListOut(
        items=[await _to_out(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/videos/tasks/{task_id}", response_model=VideoTaskOut)
async def get_video_task(task_id: str) -> VideoTaskOut:
    db = get_db()
    t = await db.get_video_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    # 若未结束，主动同步一次远端状态（快速反馈，不等 worker tick）
    if t.status in ("queued", "running") and t.provider_task_id and settings.ark_api_key:
        try:
            payload = await _seedance().fetch_task(t.provider_task_id, api_key=settings.ark_api_key)
            new_status = payload.get("status")
            if new_status and new_status != t.status:
                await db.update_video_task(
                    t.id, status=new_status, updated_at=datetime.now().isoformat()
                )
                t = await db.get_video_task(task_id)
                assert t is not None
        except Exception:  # noqa: BLE001
            pass
    return await _to_out(t)


@router.post("/videos/tasks/{task_id}/cancel", response_model=VideoTaskOut)
async def cancel_video_task(task_id: str) -> VideoTaskOut:
    db = get_db()
    t = await db.get_video_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status not in ("queued",):
        raise HTTPException(status_code=400, detail=f"当前状态不支持取消: {t.status}（仅 queued 可取消）")
    if not t.provider_task_id:
        raise HTTPException(status_code=500, detail="任务尚未拿到远端 id")
    try:
        await _seedance().delete_task(t.provider_task_id, api_key=settings.ark_api_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"取消失败: {e}") from e
    await db.update_video_task(
        t.id, status="cancelled",
        updated_at=datetime.now().isoformat(),
        completed_at=datetime.now().isoformat(),
    )
    t = await db.get_video_task(task_id)
    assert t is not None
    return await _to_out(t)


@router.delete("/videos/tasks/{task_id}")
async def delete_video_task(task_id: str) -> dict:
    db = get_db()
    t = await db.get_video_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    # 同步通知远端删除（非 queued 也调用，由远端决定是否真的删除；忽略错误）
    if t.provider_task_id and settings.ark_api_key:
        try:
            await _seedance().delete_task(t.provider_task_id, api_key=settings.ark_api_key)
        except Exception:  # noqa: BLE001
            pass
    ok = await db.delete_video_task(task_id)
    return {"deleted": ok, "id": task_id}
