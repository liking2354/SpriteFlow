"""Prompt 拼装引擎 — sorted by type → fill slots → "\n\n".join(texts)"""

from __future__ import annotations

from .models import PromptTemplate, TemplatePreviewRequest, TemplatePreviewResult
from .db import TemplateDB


async def assemble_prompt(
    db: TemplateDB,
    template_ids: list[str],
    slot_values: dict[str, str] | None = None,
) -> str:
    """拼装完整 Prompt — 核心算法

    1. 加载所有模版
    2. 按 type.sort_priority 排序
    3. 用 slot_values 填充各模版的占位符
    4. 用 "\n\n" 拼接

    Args:
        db: 模板数据库
        template_ids: 需要的模版 ID 列表
        slot_values: {slot_name: value} 填充字典
    """
    values = slot_values or {}
    templates: list[PromptTemplate] = []
    for tid in template_ids:
        t = await db.get(tid)
        if t:
            templates.append(t)

    # 按 type 排序
    templates.sort(key=lambda t: t.type.sort_priority)

    parts: list[str] = []
    for t in templates:
        text = t.text
        # 填充占位符 {slot_name}
        for slot in t.slots:
            val = values.get(slot.name, slot.default)
            text = text.replace(f"{{{slot.name}}}", val)
        if text.strip():
            parts.append(text.strip())

    return "\n\n".join(parts)


async def preview_prompt(
    db: TemplateDB,
    req: TemplatePreviewRequest,
) -> TemplatePreviewResult:
    """预览拼装结果（带分层信息）"""
    values = req.slot_values or {}
    templates: list[PromptTemplate] = []
    for tid in req.template_ids:
        t = await db.get(tid)
        if t:
            templates.append(t)

    templates.sort(key=lambda t: t.type.sort_priority)

    layers: list[dict] = []
    parts: list[str] = []
    for t in templates:
        text = t.text
        for slot in t.slots:
            val = values.get(slot.name, slot.default)
            text = text.replace(f"{{{slot.name}}}", val)
        layers.append({
            "template_id": t.id,
            "template_name": t.name,
            "type": t.type.value,
            "filled_text": text.strip(),
        })
        if text.strip():
            parts.append(text.strip())

    return TemplatePreviewResult(
        layers=layers,
        final_prompt="\n\n".join(parts),
    )
