"""模板驱动生成链路测试：GenerateRequest 校验 + 模板 Prompt 拼装 + 标签生成"""
import asyncio
import os
import sys

import pytest
import pytest_asyncio
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from spriteflow.api.generate import GenerateRequest, _build_template_tags, _resolve_template_prompt
from spriteflow.templates.db import TemplateDB
from spriteflow.templates.builder import PromptBuilder
from spriteflow.api import deps


# ======================== Fixtures ========================


async def _init_db(db: TemplateDB) -> str:
    """初始化模板数据，返回 spec_id"""
    await db.connect()
    await db.init_tables()

    spec = PromptBuilder.build_default_spec()
    for layer in spec.layers:
        await db.create_layer(layer)
        for block in layer.blocks:
            await db.create_block(block, layer.id)
    await db.create_spec(spec)
    for c in PromptBuilder.build_default_characters():
        await db.create_character(c)
    for a in PromptBuilder.build_default_actions():
        await db.create_action(a)
    return spec.id


@pytest_asyncio.fixture(scope="module")
async def template_db_spec_id():
    """创建内存 TemplateDB，返回 (db, spec_id)"""
    db = TemplateDB(db_path=":memory:")
    spec_id = await _init_db(db)
    yield db, spec_id
    await db.close()


async def _inject_tdb(template_db):
    """注入全局 TemplateDB"""
    old_tdb = deps._template_db
    deps._template_db = template_db
    return old_tdb


async def _restore_tdb(old_tdb):
    deps._template_db = old_tdb


# ======================== GenerateRequest 校验 ========================


def test_request_requires_prompt_or_spec():
    """必须提供 prompt 或 spec_id 至少一项"""
    with pytest.raises(ValidationError, match="必须提供 prompt 或 spec_id"):
        GenerateRequest(mode="text2img")

    req = GenerateRequest(mode="text2img", spec_id="some_spec_id")
    assert req.spec_id == "some_spec_id"

    req = GenerateRequest(mode="img2img", prompt="a warrior")
    assert req.prompt == "a warrior"


# ======================== _build_template_tags ========================


def test_build_tags_master():
    meta = {"spec_key": "rpg_chibi", "char_key": "warrior", "stage_key": "master"}
    tags = _build_template_tags(meta)
    assert "spec:rpg_chibi" in tags
    assert "char:warrior" in tags
    assert "stage:master" in tags


def test_build_tags_action():
    meta = {"spec_key": "rpg_chibi", "char_key": "warrior", "stage_key": "walk"}
    tags = _build_template_tags(meta)
    assert "spec:rpg_chibi" in tags
    assert "char:warrior" in tags
    assert "stage:walk" in tags


def test_build_tags_empty():
    assert _build_template_tags({}) == []


# ======================== _resolve_template_prompt ========================


@pytest.mark.asyncio
async def test_resolve_master(template_db_spec_id):
    """spec + character → 拼装 master prompt + 标签元数据"""
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(
            mode="text2img",
            spec_id=spec_id,
            character_template_id="preset_warrior",
        )
        prompt, meta = await _resolve_template_prompt(req)

        assert prompt is not None
        assert len(prompt) > 100, f"拼装 prompt 应有足够长度，实际 {len(prompt)}"
        assert meta["spec_key"] == "16_bit_rpg_chibi"
        assert meta["char_key"] == "warrior"
        assert meta["stage_key"] == "master"
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_resolve_action(template_db_spec_id):
    """spec + character + action → 拼装动作 prompt"""
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(
            mode="sequential",
            spec_id=spec_id,
            character_template_id="preset_warrior",
            action_template_id="preset_walk",
        )
        prompt, meta = await _resolve_template_prompt(req)

        assert prompt is not None
        assert len(prompt) > 100
        assert meta["spec_key"] == "16_bit_rpg_chibi"
        assert meta["char_key"] == "warrior"
        assert meta["stage_key"] == "walk"
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_resolve_no_template():
    """无 spec_id → 返回 None（使用手写 prompt）"""
    req = GenerateRequest(mode="text2img", prompt="handwritten prompt")
    prompt, meta = await _resolve_template_prompt(req)
    assert prompt is None
    assert meta == {}


@pytest.mark.asyncio
async def test_resolve_nonexistent_spec_raises(template_db_spec_id):
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(mode="text2img", spec_id="nonexistent")
        from fastapi import HTTPException
        with pytest.raises(HTTPException, match="规格书不存在"):
            await _resolve_template_prompt(req)
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_resolve_nonexistent_character_raises(template_db_spec_id):
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(
            mode="text2img", spec_id=spec_id,
            character_template_id="nonexistent",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException, match="角色模板不存在"):
            await _resolve_template_prompt(req)
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_resolve_nonexistent_action_raises(template_db_spec_id):
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(
            mode="sequential", spec_id=spec_id,
            character_template_id="preset_warrior",
            action_template_id="nonexistent",
        )
        from fastapi import HTTPException
        with pytest.raises(HTTPException, match="动作模板不存在"):
            await _resolve_template_prompt(req)
    finally:
        await _restore_tdb(old)


# ======================== 标签组合场景 ========================


@pytest.mark.asyncio
async def test_tags_full_chain(template_db_spec_id):
    """完整标签链：用户 tag → 模板 tag → 系统 tag"""
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(
            mode="sequential",
            spec_id=spec_id,
            character_template_id="preset_warrior",
            action_template_id="preset_walk",
            tags=["project:demo", "quality:high"],
        )
        prompt, meta = await _resolve_template_prompt(req)

        tags = list(req.tags)
        tags.extend(_build_template_tags(meta))
        tags.append(f"mode:{req.mode}")
        tags.append("seq:0")

        assert "project:demo" in tags
        assert "quality:high" in tags
        assert "spec:16_bit_rpg_chibi" in tags
        assert "char:warrior" in tags
        assert "stage:walk" in tags
        assert "mode:sequential" in tags
        assert "seq:0" in tags

        # 验证顺序：用户 → 模板 → 系统
        user_end = max(tags.index("project:demo"), tags.index("quality:high"))
        tpl_start = tags.index("spec:16_bit_rpg_chibi")
        sys_start = tags.index("mode:sequential")
        assert user_end < tpl_start < sys_start, "标签顺序应为: 用户 → 模板 → 系统"
    finally:
        await _restore_tdb(old)


# ======================== 幂等性 / 兼容性 ========================


@pytest.mark.asyncio
async def test_template_prompt_is_reproducible(template_db_spec_id):
    """相同参数 → 相同 prompt（幂等性）"""
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(
            mode="text2img",
            spec_id=spec_id,
            character_template_id="preset_warrior",
            action_template_id="preset_idle",
        )
        p1, _ = await _resolve_template_prompt(req)
        p2, _ = await _resolve_template_prompt(req)
        assert p1 == p2, "模板拼装结果应幂等"
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_handwritten_prompt_still_works(template_db_spec_id):
    """不提供 spec_id 时手写 prompt 原样保留（向后兼容）"""
    tdb, spec_id = template_db_spec_id
    old = await _inject_tdb(tdb)
    try:
        req = GenerateRequest(mode="text2img", prompt="a beautiful landscape")
        prompt, meta = await _resolve_template_prompt(req)
        assert prompt is None
        assert meta == {}
    finally:
        await _restore_tdb(old)
