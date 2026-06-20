"""快捷生图 API — 不依赖 YAML，前端直接表单调用

涵盖 4 种 Seedream 能力：text2img / img2img / multi_fusion / sequential
所有调用都会持久化为 GenerationJob 任务记录。
"""

from __future__ import annotations

import asyncio
import io
import itertools
import json
import uuid
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from sse_starlette.sse import EventSourceResponse

from ..asset_hub.models import GenerationJob
from ..providers.base import Capability
from .deps import get_router, get_storage, get_db, get_template_db
from ..asset_hub.ingest import IngestPipeline

router = APIRouter()


# ============================ 请求模型 ============================


class GenerateRequest(BaseModel):
    """统一的快捷生图请求

    支持两种模式：
    1. 手写 prompt：直接提供 prompt 字段
    2. 模板驱动：提供 template_ids + slot_values，
       assemble_prompt 自动拼装 prompt（此时手写 prompt 被忽略）
    """

    mode: str = Field(..., description="text2img | img2img | multi_fusion | sequential")
    prompt: str = Field("", description="提示词（模板模式下自动拼装，手写时必填）")
    template_ids: list[str] = Field(default_factory=list, description="模板 ID 列表")
    slot_values: dict[str, str] = Field(default_factory=dict, description="模板槽位值")
    image_urls: list[str] = Field(default_factory=list)
    ref_asset_ids: list[str] = Field(default_factory=list, description="素材库内参考图 id")
    size: str = Field("2k", description="2k / 4k / 自定义如 2048x2048 / adaptive")
    width: int | None = None             # 自定义宽（与 height 配对，覆盖 size）
    height: int | None = None
    seed: int | None = None
    max_images: int = Field(1, ge=1, le=15)
    web_search: bool = False
    watermark: bool = False
    model: str | None = Field(None, description="覆盖默认模型（如 openai/gpt-image-1）")
    save_as_asset: bool = True
    tags: list[str] = Field(default_factory=list)
    group_id: str | None = None

    @model_validator(mode="after")
    def _check_prompt_or_template(self):
        if not self.prompt and not self.template_ids:
            raise ValueError("必须提供 prompt 或 template_ids 至少一项")
        return self


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


# ============================ 批量生成 ============================


class BatchGenerateRequest(BaseModel):
    """批量生成请求：角色 × 动作矩阵"""
    character_template_ids: list[str] = Field(..., min_length=1, description="角色模板 ID 列表")
    action_template_ids: list[str] = Field(..., min_length=1, description="动作模板 ID 列表")
    slot_values: dict[str, str] = Field(default_factory=dict, description="模板槽位值")
    generate_count_per: int = Field(1, ge=1, le=15, description="每个组合生成图片数")
    group_id: str | None = Field(None, description="素材分组 ID")
    concurrent: int = Field(3, ge=1, le=10, description="并发数")


class BatchGenerateResponse(BaseModel):
    batch_id: str
    total_jobs: int
    jobs: list[dict]
    status: str


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


# ============================ 错误分类（前端友好提示） ============================

def _categorize_error(error: Exception) -> tuple[str, str]:
    """将异常分类为用户友好的错误码 + 消息

    Returns:
        (code, message) — code 供前端识别，message 为用户可读提示
    """
    msg = str(error)

    # API Key 缺失
    if "缺少 ARK_API_KEY" in msg or "缺少 API_KEY" in msg:
        return ("AUTH_KEY_MISSING", "API 密钥未配置，请在 .env 中设置 ARK_API_KEY")
    if "401" in msg or "Unauthorized" in msg or "unauthorized" in msg.lower():
        return ("AUTH_INVALID", "API 密钥无效或已过期，请检查配置")

    # 内容安全检测
    if "SensitiveContentDetected" in msg or "内容安全" in msg:
        if "prompt" in msg.lower() or "提示词" in msg:
            return ("CONTENT_MODERATION_PROMPT", "提示词触发内容安全过滤，请修改提示词")
        if "input" in msg.lower() or "参考图" in msg:
            return ("CONTENT_MODERATION_INPUT", "参考图被内容安全系统拦截，请更换图片")
        if "output" in msg.lower() or "生成结果" in msg:
            return ("CONTENT_MODERATION_OUTPUT", "生成结果触发内容安全过滤，请重试")
        return ("CONTENT_MODERATION", "内容被安全系统拦截，请调整输入后重试")

    # Provider 错误
    if "Seedream API 错误" in msg or "provider" in msg.lower():
        return ("PROVIDER_ERROR", "AI 生成服务暂时不可用，请稍后重试")

    # 下载超时
    if "下载" in msg and ("超时" in msg or "timeout" in msg.lower()):
        return ("DOWNLOAD_TIMEOUT", "图片下载超时，请检查网络后重试")

    # 请求超时
    if "timeout" in msg.lower() or "超时" in msg:
        return ("TIMEOUT", "请求超时，请稍后重试")

    # 网络错误
    if "connect" in msg.lower() or "network" in msg.lower() or "网络" in msg or "dns" in msg.lower():
        return ("NETWORK_ERROR", "网络连接失败，请检查网络后重试")

    # 模板相关
    if "模板" in msg or "template" in msg.lower():
        return ("TEMPLATE_ERROR", f"模板错误：{msg}"[:120])

    return ("UNKNOWN", msg[:200])


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
    return req.size or "2k"


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
    if req.model:
        payload["model"] = req.model
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
            "template_ids": req.template_ids,
            "slot_values": req.slot_values,
        },
        ref_image_urls=req.image_urls or [],
        ref_asset_ids=req.ref_asset_ids or [],
        status="running",
    )


# ============================ 模板解析 ============================


def _build_template_tags(meta: dict) -> list[str]:
    """从模板元数据构建标签列表：spec:{key}, char:{key}, stage:{key|master}"""
    tags: list[str] = []
    if meta.get("spec_key"):
        tags.append(f"spec:{meta['spec_key']}")
    if meta.get("char_key"):
        tags.append(f"char:{meta['char_key']}")
    if meta.get("stage_key"):
        tags.append(f"stage:{meta['stage_key']}")
    elif meta.get("char_key"):
        # 有角色但无动作 → 母版阶段
        tags.append("stage:master")
    return tags


async def _resolve_template_prompt(req: GenerateRequest) -> tuple[str | None, dict]:
    """解析模板参数，调用 assemble_prompt 拼装 prompt

    Returns:
        (effective_prompt, template_meta)
        - 若未提供 template_ids，返回 (None, {}) 表示使用手写 prompt
        - template_meta 携带模板名称等元数据用于标签
    """
    if not req.template_ids:
        return None, {}

    try:
        tdb = get_template_db()
        if tdb is None:
            return None, {}

        from ..templates.builder import assemble_prompt
        prompt = await assemble_prompt(tdb, req.template_ids, req.slot_values)

        meta: dict = {"template_ids": req.template_ids}

        # 收集模板名称作为标签
        names = []
        for tid in req.template_ids:
            tpl = await tdb.get(tid)
            if tpl:
                names.append(tpl.name)
                if tpl.type.value == "character":
                    meta["char_name"] = tpl.name
                elif tpl.type.value == "action":
                    meta["action_name"] = tpl.name
        meta["template_names"] = names

        return prompt, meta

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"模板拼装失败: {e}")


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
            # 模板解析：拼装 prompt + 构建标签元数据
            template_prompt, template_meta = await _resolve_template_prompt(req)
            effective_prompt = template_prompt or req.prompt

            refs = await _resolve_refs(req)
            _validate_refs(req.mode, refs)
            router_inst = get_router()
            payload = _build_payload(cap, req, refs)
            # 模板 prompt 覆盖手写 prompt
            payload["prompt"] = effective_prompt
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

            # 自动推断 group_id
            group_id = req.group_id
            if not group_id and template_meta.get("auto_group_id"):
                group_id = template_meta["auto_group_id"]

            asset_ids: list[str] = []
            for idx, img in enumerate(images):
                if not req.save_as_asset:
                    continue
                tags = list(req.tags)
                if template_meta:
                    tags.extend(_build_template_tags(template_meta))
                tags.append(f"mode:{req.mode}")
                if req.mode == "sequential" and len(images) > 1:
                    tags.append(f"seq:{idx}")
                info = await _persist_image(img, effective_prompt, tags, group_id)
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

            # 模板解析
            template_prompt, template_meta = await _resolve_template_prompt(req)
            effective_prompt = template_prompt or req.prompt

            refs = await _resolve_refs(req)
            payload = _build_payload(cap, req, refs, run_id=job.id)
            payload["prompt"] = effective_prompt
            result = await router_inst.route(cap, payload)

            images = result.get("images") or []
            persisted: list[dict[str, Any]] = []
            asset_ids: list[str] = []

            # 自动推断 group_id
            group_id = req.group_id
            if not group_id and template_meta.get("auto_group_id"):
                group_id = template_meta["auto_group_id"]

            if req.save_as_asset:
                for idx, img in enumerate(images):
                    tags = list(req.tags)
                    if template_meta:
                        tags.extend(_build_template_tags(template_meta))
                    tags.extend(["mode:sequential", f"seq:{idx}"])
                    info = await _persist_image(img, effective_prompt, tags, group_id)
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


# ============================ 批量生成引擎 ============================

_batches: dict[str, dict] = {}


def _update_batch_job_status(batch_id: str, job_id: str, status: str) -> None:
    """更新批量任务中单个 job 的状态，并检查整个 batch 是否完成"""
    batch = _batches.get(batch_id)
    if not batch:
        return
    for entry in batch["matrix"]:
        if entry["job_id"] == job_id:
            entry["status"] = status
            break
    if status == "completed":
        batch["completed"] += 1
    elif status == "failed":
        batch["failed"] += 1

    # 检查是否全部完成
    if batch["completed"] + batch["failed"] >= batch["total_jobs"]:
        if batch["failed"] == 0:
            batch["status"] = "completed"
        elif batch["completed"] == 0:
            batch["status"] = "failed"
        else:
            batch["status"] = "partial"


async def _expand_batch_matrix(req: BatchGenerateRequest) -> tuple[list[dict], dict]:
    """校验参数并展开 char × action 矩阵

    纯逻辑函数，只依赖 TemplateDB 单例（不依赖 AssetDB / CapabilityRouter），
    方便单元测试。

    Returns:
        (entries, template_meta) — entries 是 [{char_tpl, action_tpl}, ...]
    """
    tdb = get_template_db()

    # 校验角色（type=character）
    chars: list = []
    for cid in req.character_template_ids:
        char = await tdb.get(cid)
        if not char:
            raise HTTPException(400, f"角色模板不存在: {cid}")
        chars.append(char)

    # 校验动作（type=action）
    actions: list = []
    for aid in req.action_template_ids:
        action = await tdb.get(aid)
        if not action:
            raise HTTPException(400, f"动作模板不存在: {aid}")
        actions.append(action)

    if not chars:
        raise HTTPException(400, "至少需要一个角色模板")
    if not actions:
        raise HTTPException(400, "至少需要一个动作模板")

    # 展开矩阵
    entries = [{"char": char, "action": action}
               for char, action in itertools.product(chars, actions)]

    return entries, {"group_id": req.group_id}


@router.post("/generate/batch", response_model=BatchGenerateResponse)
async def batch_generate(req: BatchGenerateRequest):
    """批量生成：角色 × 动作 矩阵式生产

    输入：角色模板列表 + 动作模板列表
    内部展开为 char × action 矩阵，每个组合创建一个 GenerationJob。
    使用信号量控制并发数，任务在后台异步执行。

    返回 batch_id，前端可轮询 /api/generate/batch/{batch_id} 获取进度矩阵。
    """
    # 校验 + 矩阵展开（纯逻辑，只依赖 TemplateDB）
    entries, meta = await _expand_batch_matrix(req)

    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    db = get_db()
    router_inst = get_router()

    # 为每个组合创建 GenerationJob
    matrix: list[dict] = []
    job_reqs: list[tuple[Any, Any, GenerateRequest, GenerationJob]] = []

    for entry in entries:
        gen_req = GenerateRequest(
            mode="sequential",
            template_ids=[entry["char"].id, entry["action"].id],
            slot_values=req.slot_values,
            max_images=req.generate_count_per,
            save_as_asset=True,
            tags=[],
            group_id=req.group_id,
        )
        job = _make_job_record(gen_req)
        await db.create_job(job)
        job_reqs.append((entry["char"], entry["action"], gen_req, job))
        matrix.append({
            "job_id": job.id,
            "char_id": entry["char"].id,
            "char_name": entry["char"].name,
            "action_id": entry["action"].id,
            "action_name": entry["action"].name,
            "status": "pending",
        })

    total = len(job_reqs)

    # 存储批量状态
    _batches[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total_jobs": total,
        "completed": 0,
        "failed": 0,
        "matrix": matrix,
    }

    # 并发控制
    sem = asyncio.Semaphore(req.concurrent)

    async def _run_one(char: Any, action: Any, gen_req: GenerateRequest, job: GenerationJob) -> None:
        async with sem:
            try:
                # 模板解析
                template_prompt, template_meta = await _resolve_template_prompt(gen_req)
                effective_prompt = template_prompt or gen_req.prompt

                cap = _MODE_TO_CAP.get(gen_req.mode)
                refs = await _resolve_refs(gen_req)
                _validate_refs(gen_req.mode, refs)

                payload = _build_payload(cap, gen_req, refs)
                payload["prompt"] = effective_prompt
                result = await router_inst.route(cap, payload)

                images = result.get("images") or (
                    [result["image"]] if result.get("image") else []
                )

                if not images:
                    await db.update_job(
                        job.id, status="failed", error="provider 未返回图片",
                        finished_at=datetime.now().isoformat(),
                    )
                    _update_batch_job_status(batch_id, job.id, "failed")
                    return

                group_id = gen_req.group_id
                if not group_id and template_meta.get("auto_group_id"):
                    group_id = template_meta["auto_group_id"]

                asset_ids: list[str] = []
                for idx, img in enumerate(images):
                    if not gen_req.save_as_asset:
                        continue
                    tags = list(gen_req.tags)
                    if template_meta:
                        tags.extend(_build_template_tags(template_meta))
                    tags.append(f"mode:{gen_req.mode}")
                    if gen_req.mode == "sequential" and len(images) > 1:
                        tags.append(f"seq:{idx}")
                    info = await _persist_image(img, effective_prompt, tags, group_id)
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
                _update_batch_job_status(batch_id, job.id, "completed")

            except Exception as e:
                await db.update_job(
                    job.id, status="failed", error=str(e),
                    finished_at=datetime.now().isoformat(),
                )
                _update_batch_job_status(batch_id, job.id, "failed")

    # 启动后台任务
    for char, action, gen_req, job in job_reqs:
        asyncio.create_task(_run_one(char, action, gen_req, job))

    return BatchGenerateResponse(
        batch_id=batch_id,
        total_jobs=total,
        jobs=matrix,
        status="started",
    )


@router.get("/generate/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    """获取批量生成进度矩阵

    返回每个组合（char × action）的状态矩阵：
    - pending: 等待执行
    - running: 正在生成
    - completed: 已完成
    - failed: 失败
    """
    batch = _batches.get(batch_id)
    if not batch:
        raise HTTPException(404, f"批量任务不存在或已过期: {batch_id}")

    # 从 DB 刷新每个 job 的状态（best-effort）
    try:
        db = get_db()
        for entry in batch["matrix"]:
            try:
                job = await db.get_job(entry["job_id"])
                if job:
                    entry["status"] = job.status
            except Exception:
                pass
    except Exception:
        pass

    return {
        "batch_id": batch_id,
        "status": batch["status"],
        "total_jobs": batch["total_jobs"],
        "completed": batch["completed"],
        "failed": batch["failed"],
        "matrix": batch["matrix"],
    }


# ============================ VFX 特效生成 ============================

class VFXGenerateRequest(BaseModel):
    """VFX 特效生成请求"""
    vfx_template_id: str = ""
    seed: int | None = None
    group_id: str | None = None


class VFXFrameEntry(BaseModel):
    """VFX 单帧状态"""
    frame_index: int = 0
    job_id: str = ""
    status: str = "pending"
    asset_id: str | None = None
    url: str | None = None


class VFXGenerateResponse(BaseModel):
    """VFX 生成响应"""
    vfx_id: str = ""
    batch_id: str = ""
    vfx_name: str = ""
    total_frames: int = 0
    frames: list[dict] = Field(default_factory=list)
    status: str = "started"


_vfx_batches: dict[str, dict] = {}


@router.post("/generate/vfx", response_model=VFXGenerateResponse)
async def generate_vfx(req: VFXGenerateRequest):
    """VFX 特效生成：选模板 → 并发生成 N 帧

    每帧作为一个独立的 text2img 任务，使用 VFX 模板中的 prompt 和画布尺寸。
    """
    tdb = get_template_db()
    vfx = await tdb.get_vfx(req.vfx_template_id)
    if not vfx:
        raise HTTPException(404, f"VFX 模板不存在: {req.vfx_template_id}")

    batch_id = f"vfx_{uuid.uuid4().hex[:12]}"
    db = get_db()
    router_inst = get_router()

    frames: list[dict] = []
    job_reqs: list[tuple[int, GenerateRequest, GenerationJob]] = []

    for i in range(vfx.frames):
        job = GenerationJob(
            mode="text2img",
            prompt=vfx.prompt,
            params={
                "width": vfx.canvas_width,
                "height": vfx.canvas_height,
                "seed": req.seed,
                "max_images": 1,
                "tags": ["vfx", vfx.key, f"frame:{i}"],
                "group_id": req.group_id,
                "source": "vfx",
            },
        )
        await db.create_job(job)

        gen_req = GenerateRequest(
            mode="text2img",
            prompt=vfx.prompt,
            width=vfx.canvas_width,
            height=vfx.canvas_height,
            seed=req.seed,
            max_images=1,
            tags=["vfx", vfx.key, f"frame:{i}"],
            group_id=req.group_id,
            save_as_asset=True,
        )

        frames.append({
            "frame_index": i,
            "job_id": job.id,
            "status": "pending",
            "asset_id": None,
            "url": None,
        })
        job_reqs.append((i, gen_req, job))

    _vfx_batches[batch_id] = {
        "batch_id": batch_id,
        "vfx_id": vfx.id,
        "vfx_name": vfx.name,
        "status": "running",
        "total_frames": vfx.frames,
        "completed": 0,
        "failed": 0,
        "frames": frames,
    }

    sem = asyncio.Semaphore(4)

    async def _run_one(frame_idx: int, gen_req: GenerateRequest, job: GenerationJob):
        async with sem:
            try:
                await db.update_job(job.id, status="running")
                _update_vfx_frame(batch_id, job.id, "running")

                router_inst = get_router()
                payload = _build_payload(Capability.TEXT2IMG, gen_req, [])
                result = await router_inst.route(Capability.TEXT2IMG, payload)

                images = result.get("images") or (
                    [result["image"]] if result.get("image") else []
                )
                if not images:
                    await db.update_job(
                        job.id, status="failed", error="provider 未返回图片",
                        finished_at=datetime.now().isoformat(),
                    )
                    _update_vfx_frame(batch_id, job.id, "failed")
                    return

                asset_ids: list[str] = []
                for idx, img in enumerate(images):
                    if not gen_req.save_as_asset:
                        continue
                    tags = list(gen_req.tags or [])
                    info = await _persist_image(img, gen_req.prompt, tags, gen_req.group_id)
                    if info.get("asset_id"):
                        asset_ids.append(info["asset_id"])

                first_asset = asset_ids[0] if asset_ids else None
                await db.update_job(
                    job.id,
                    status="completed",
                    asset_ids=asset_ids,
                    model=result.get("model"),
                    usage=result.get("usage", {}),
                    finished_at=datetime.now().isoformat(),
                )
                _update_vfx_frame(batch_id, job.id, "completed", asset_id=first_asset)

            except Exception as e:
                await db.update_job(
                    job.id, status="failed", error=str(e),
                    finished_at=datetime.now().isoformat(),
                )
                _update_vfx_frame(batch_id, job.id, "failed")

    for frame_idx, gen_req, job in job_reqs:
        asyncio.create_task(_run_one(frame_idx, gen_req, job))

    return VFXGenerateResponse(
        vfx_id=vfx.id,
        batch_id=batch_id,
        vfx_name=vfx.name,
        total_frames=vfx.frames,
        frames=frames,
        status="started",
    )


def _update_vfx_frame(batch_id: str, job_id: str, status: str, asset_id: str | None = None) -> None:
    """更新 VFX 批量任务中单帧状态"""
    batch = _vfx_batches.get(batch_id)
    if not batch:
        return
    for frame in batch["frames"]:
        if frame["job_id"] == job_id:
            frame["status"] = status
            if asset_id:
                frame["asset_id"] = asset_id
            break
    if status == "completed":
        batch["completed"] += 1
    elif status == "failed":
        batch["failed"] += 1

    total = batch["total_frames"]
    done = batch["completed"] + batch["failed"]
    if done >= total:
        if batch["failed"] == 0:
            batch["status"] = "completed"
        elif batch["completed"] == 0:
            batch["status"] = "failed"
        else:
            batch["status"] = "partial"


@router.get("/generate/vfx/{batch_id}")
async def get_vfx_status(batch_id: str):
    """获取 VFX 生成进度"""
    batch = _vfx_batches.get(batch_id)
    if not batch:
        raise HTTPException(404, f"VFX 任务不存在或已过期: {batch_id}")

    # best-effort DB refresh
    try:
        db = get_db()
        for frame in batch["frames"]:
            try:
                job = await db.get_job(frame["job_id"])
                if job:
                    frame["status"] = job.status
                    if job.asset_ids:
                        frame["asset_id"] = job.asset_ids[0]
            except Exception:
                pass
    except Exception:
        pass

    return {
        "batch_id": batch_id,
        "vfx_id": batch["vfx_id"],
        "vfx_name": batch["vfx_name"],
        "status": batch["status"],
        "total_frames": batch["total_frames"],
        "completed": batch["completed"],
        "failed": batch["failed"],
        "frames": batch["frames"],
    }
