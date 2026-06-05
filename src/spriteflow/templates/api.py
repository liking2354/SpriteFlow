"""模板系统 API 端点

提供 Spec / Layer / Block / Character / Action / VFX / Pipeline 的完整 CRUD
以及 Prompt 预览和批量生成入口
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from .models import (
    SpriteSpec, PromptLayer, PromptBlock, BlockCategory,
    CharacterTemplate, ActionTemplate, VFXTemplate, StagePipeline,
    PromptAssembly, PromptAssemblyResult,
    BatchGenerateRequest,
)
from .db import TemplateDB
from .builder import PromptBuilder

# 模板数据库通过 deps 注入
_template_db: TemplateDB | None = None

router = APIRouter(prefix="/api/templates", tags=["templates"])


def set_template_db(db: TemplateDB) -> None:
    global _template_db
    _template_db = db


def get_template_db() -> TemplateDB:
    if _template_db is None:
        raise RuntimeError("模板数据库未初始化")
    return _template_db


# ============================ SpriteSpec ============================

@router.get("/specs")
async def list_specs() -> list[SpriteSpec]:
    db = get_template_db()
    return await db.list_specs()


@router.get("/specs/{spec_id}")
async def get_spec(spec_id: str) -> SpriteSpec:
    db = get_template_db()
    spec = await db.get_spec(spec_id)
    if not spec:
        raise HTTPException(404, f"规格书不存在: {spec_id}")
    return spec


@router.post("/specs")
async def create_spec(spec: SpriteSpec) -> SpriteSpec:
    db = get_template_db()
    now = datetime.now().isoformat()
    spec.created_at = now
    spec.updated_at = now
    # 确保每个 layer 中的 blocks 有 id
    for layer in spec.layers:
        if not layer.id:
            layer.id = f"layer_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        layer.created_at = now
        layer.updated_at = now
        for block in layer.blocks:
            if not block.id:
                block.id = f"block_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            block.created_at = now
            block.updated_at = now
    # 保存 layers 和 spec
    for layer in spec.layers:
        _ = await db.create_layer(layer)
        for block in layer.blocks:
            _ = await db.create_block(block, layer.id)
    return await db.create_spec(spec)


@router.put("/specs/{spec_id}")
async def update_spec(spec_id: str, spec: SpriteSpec) -> SpriteSpec:
    db = get_template_db()
    existing = await db.get_spec(spec_id)
    if not existing:
        raise HTTPException(404, f"规格书不存在: {spec_id}")
    spec.id = spec_id
    spec.updated_at = datetime.now().isoformat()
    spec.version = existing.version + 1
    return await db.create_spec(spec)


@router.delete("/specs/{spec_id}")
async def delete_spec(spec_id: str):
    db = get_template_db()
    await db.delete_spec(spec_id)
    return {"ok": True}


@router.post("/specs/{spec_id}/clone")
async def clone_spec(spec_id: str, name: str) -> SpriteSpec:
    """克隆规格书（A/B 测试用）"""
    db = get_template_db()
    orig = await db.get_spec(spec_id)
    if not orig:
        raise HTTPException(404, f"规格书不存在: {spec_id}")
    now = datetime.now().isoformat()
    new_id = f"spec_{now.strftime('%Y%m%d%H%M%S%f')}"
    orig.id = new_id
    orig.name = name
    orig.version = 1
    orig.created_at = now
    orig.updated_at = now
    for layer in orig.layers:
        old_lid, old_sorted = layer.id, layer.sort_order
        layer.id = f"layer_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        for block in layer.blocks:
            old_bid = block.id
            block.id = f"block_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    return await db.create_spec(orig)


# ============================ PromptLayer ============================

@router.get("/layers")
async def list_layers(category: str | None = None) -> list[PromptLayer]:
    db = get_template_db()
    return await db.list_layers(category)


@router.post("/layers")
async def create_layer(layer: PromptLayer) -> PromptLayer:
    db = get_template_db()
    now = datetime.now().isoformat()
    if not layer.id:
        layer.id = f"layer_{now.strftime('%Y%m%d%H%M%S%f')}"
    layer.created_at = now
    layer.updated_at = now
    return await db.create_layer(layer)


@router.put("/layers/{layer_id}")
async def update_layer(layer_id: str, layer: PromptLayer) -> PromptLayer:
    db = get_template_db()
    layer.id = layer_id
    layer.updated_at = datetime.now().isoformat()
    await db.update_layer(layer)
    return layer


@router.delete("/layers/{layer_id}")
async def delete_layer(layer_id: str):
    db = get_template_db()
    await db.delete_layer(layer_id)
    return {"ok": True}


# ============================ PromptBlock ============================

@router.post("/layers/{layer_id}/blocks")
async def create_block(layer_id: str, block: PromptBlock) -> PromptBlock:
    db = get_template_db()
    now = datetime.now().isoformat()
    if not block.id:
        block.id = f"block_{now.strftime('%Y%m%d%H%M%S%f')}"
    block.created_at = now
    block.updated_at = now
    return await db.create_block(block, layer_id)


@router.put("/blocks/{block_id}")
async def update_block(block_id: str, block: PromptBlock) -> PromptBlock:
    db = get_template_db()
    block.id = block_id
    block.updated_at = datetime.now().isoformat()
    await db.update_block(block)
    return block


@router.delete("/blocks/{block_id}")
async def delete_block(block_id: str):
    db = get_template_db()
    await db.delete_block(block_id)
    return {"ok": True}


# ============================ CharacterTemplate ============================

@router.get("/characters")
async def list_characters(class_type: str | None = None) -> list[CharacterTemplate]:
    db = get_template_db()
    return await db.list_characters(class_type)


@router.post("/characters")
async def create_character(ct: CharacterTemplate) -> CharacterTemplate:
    db = get_template_db()
    now = datetime.now().isoformat()
    if not ct.id:
        ct.id = f"char_{now.strftime('%Y%m%d%H%M%S%f')}"
    ct.created_at = now
    ct.updated_at = now
    return await db.create_character(ct)


@router.put("/characters/{char_id}")
async def update_character(char_id: str, ct: CharacterTemplate) -> CharacterTemplate:
    db = get_template_db()
    ct.id = char_id
    ct.updated_at = datetime.now().isoformat()
    await db.update_character(ct)
    return ct


@router.delete("/characters/{char_id}")
async def delete_character(char_id: str):
    db = get_template_db()
    await db.delete_character(char_id)
    return {"ok": True}


# ============================ ActionTemplate ============================

@router.get("/actions")
async def list_actions() -> list[ActionTemplate]:
    db = get_template_db()
    return await db.list_actions()


@router.post("/actions")
async def create_action(at: ActionTemplate) -> ActionTemplate:
    db = get_template_db()
    now = datetime.now().isoformat()
    if not at.id:
        at.id = f"act_{now.strftime('%Y%m%d%H%M%S%f')}"
    at.created_at = now
    at.updated_at = now
    return await db.create_action(at)


@router.put("/actions/{action_id}")
async def update_action(action_id: str, at: ActionTemplate) -> ActionTemplate:
    db = get_template_db()
    at.id = action_id
    at.updated_at = datetime.now().isoformat()
    await db.update_action(at)
    return at


@router.delete("/actions/{action_id}")
async def delete_action(action_id: str):
    db = get_template_db()
    await db.delete_action(action_id)
    return {"ok": True}


# ============================ VFXTemplate ============================

@router.get("/vfx")
async def list_vfx() -> list[VFXTemplate]:
    db = get_template_db()
    return await db.list_vfx()


@router.post("/vfx")
async def create_vfx(vfx: VFXTemplate) -> VFXTemplate:
    db = get_template_db()
    now = datetime.now().isoformat()
    if not vfx.id:
        vfx.id = f"vfx_{now.strftime('%Y%m%d%H%M%S%f')}"
    vfx.created_at = now
    vfx.updated_at = now
    return await db.create_vfx(vfx)


@router.put("/vfx/{vfx_id}")
async def update_vfx(vfx_id: str, vfx: VFXTemplate) -> VFXTemplate:
    db = get_template_db()
    vfx.id = vfx_id
    vfx.updated_at = datetime.now().isoformat()
    await db.update_vfx(vfx)
    return vfx


@router.delete("/vfx/{vfx_id}")
async def delete_vfx(vfx_id: str):
    db = get_template_db()
    await db.delete_vfx(vfx_id)
    return {"ok": True}


# ============================ StagePipeline ============================

@router.get("/pipelines")
async def list_pipelines() -> list[StagePipeline]:
    db = get_template_db()
    return await db.list_pipelines()


@router.post("/pipelines")
async def create_pipeline(pipeline: StagePipeline) -> StagePipeline:
    db = get_template_db()
    now = datetime.now().isoformat()
    if not pipeline.id:
        pipeline.id = f"pipeline_{now.strftime('%Y%m%d%H%M%S%f')}"
    pipeline.created_at = now
    pipeline.updated_at = now
    return await db.create_pipeline(pipeline)


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: str):
    db = get_template_db()
    await db.delete_pipeline(pipeline_id)
    return {"ok": True}


# ============================ Prompt Preview ============================

@router.post("/preview")
async def preview_prompt(req: PromptAssembly) -> PromptAssemblyResult:
    """预览完整拼装后的 Prompt"""
    db = get_template_db()
    builder = PromptBuilder(db)
    return await builder.assemble(req)


# ============================ 初始化预置模板 ============================

@router.post("/init-presets")
async def init_presets() -> dict[str, Any]:
    """初始化预置模板数据（默认 Spec + 6 角色 + 7 动作 + 4 VFX）"""
    db = get_template_db()

    # 检查是否已有数据
    existing = await db.list_specs()
    if existing:
        return {"ok": True, "message": f"已有 {len(existing)} 个规格书，跳过初始化", "count": len(existing)}

    # 规格书
    spec = PromptBuilder.build_default_spec()
    for layer in spec.layers:
        _ = await db.create_layer(layer)
        for block in layer.blocks:
            _ = await db.create_block(block, layer.id)
    _ = await db.create_spec(spec)

    # 角色
    chars = PromptBuilder.build_default_characters()
    for c in chars:
        _ = await db.create_character(c)

    # 动作
    actions = PromptBuilder.build_default_actions()
    for a in actions:
        _ = await db.create_action(a)

    # VFX
    vfx_list = PromptBuilder.build_default_vfx()
    for v in vfx_list:
        _ = await db.create_vfx(v)

    return {
        "ok": True,
        "specs": 1,
        "characters": len(chars),
        "actions": len(actions),
        "vfx": len(vfx_list),
    }
