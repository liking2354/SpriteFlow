"""模板系统 API — 统一 PromptTemplate 单表 CRUD + 拼装预览 + 预设初始化"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from .models import PromptTemplate, PromptSlot, TemplateType, TemplatePreviewRequest, TemplatePreviewResult
from .db import TemplateDB
from .builder import assemble_prompt, preview_prompt
from .seed import PRESET_TEMPLATES
from ..api.deps import get_template_db

router = APIRouter()


def _get_db() -> TemplateDB:
    return get_template_db()


# ── 预设初始化 ──

@router.post("/templates/init-presets")
async def init_presets(force: bool = False) -> dict[str, Any]:
    db = _get_db()
    count = await db.count()
    if count > 0 and not force:
        return {"ok": True, "message": f"已有 {count} 个模板，跳过初始化。传 force=true 强制刷新", "count": count}

    created = 0
    for t in PRESET_TEMPLATES:
        await db.create(t)  # INSERT OR REPLACE 语义
        created += 1

    action = "强制刷新" if force else "首次注入"
    return {"ok": True, "message": f"{action} {created} 个预置模板", "count": created}


# ── CRUD ──

@router.get("/templates")
async def list_templates(
    type: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    db = _get_db()
    total = await db.count(type_filter=type)
    templates = await db.list(type_filter=type, limit=limit, offset=offset)
    dumped = [t.model_dump() for t in templates]
    return {"templates": dumped, "total": total, "limit": limit, "offset": offset}


@router.get("/templates/{template_id}")
async def get_template(template_id: str) -> PromptTemplate:
    db = _get_db()
    t = await db.get(template_id)
    if not t:
        raise HTTPException(404, f"模板不存在: {template_id}")
    return t


@router.post("/templates")
async def create_template(template: PromptTemplate) -> PromptTemplate:
    db = _get_db()
    now = datetime.now()
    if not template.id or template.id.startswith("tmpl_") is False:
        template.id = f"tmpl_{now.strftime('%Y%m%d%H%M%S%f')}"
    template.created_at = now.isoformat()
    template.updated_at = now.isoformat()
    return await db.create(template)


@router.put("/templates/{template_id}")
async def update_template(template_id: str, template: PromptTemplate) -> PromptTemplate:
    db = _get_db()
    existing = await db.get(template_id)
    if not existing:
        raise HTTPException(404, f"模板不存在: {template_id}")
    template.id = template_id
    template.updated_at = datetime.now().isoformat()
    return await db.update(template)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    db = _get_db()
    await db.delete(template_id)
    return {"ok": True}


@router.post("/templates/batch-delete")
async def batch_delete_templates(req: dict[str, Any]) -> dict[str, Any]:
    ids = req.get("ids", [])
    if not ids:
        raise HTTPException(400, "请提供要删除的模板 ID 列表")
    db = _get_db()
    deleted = await db.batch_delete(ids)
    return {"ok": True, "deleted": deleted}


# ── 拼装预览 ──

@router.post("/templates/preview")
async def preview(req: TemplatePreviewRequest) -> TemplatePreviewResult:
    db = _get_db()
    return await preview_prompt(db, req)


# ── 按 type 分组列出（方便前端下拉） ──

@router.get("/templates/by-type/{template_type}")
async def list_by_type(template_type: str) -> dict[str, Any]:
    db = _get_db()
    templates = await db.list(type_filter=template_type)
    dumped = [t.model_dump() for t in templates]
    return {"templates": dumped, "total": len(dumped)}
