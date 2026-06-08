"""批量生成引擎测试：矩阵展开 + 并发控制 + 进度查询"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from spriteflow.api.generate import (
    _batches,
    _update_batch_job_status,
    _expand_batch_matrix,
    get_batch_status,
)
from spriteflow.templates.db import TemplateDB
from spriteflow.templates.builder import PromptBuilder
from spriteflow.templates.models import BatchGenerateRequest
from spriteflow.api import deps
from fastapi import HTTPException


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
async def tdb_with_spec():
    """创建内存 TemplateDB + 预置数据，返回 (db, spec_id)"""
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


def _cleanup_batch(batch_id: str) -> None:
    """清理批量状态记录"""
    _batches.pop(batch_id, None)


# ======================== _update_batch_job_status ========================


def test_update_status_single_job():
    """单个 job 状态更新"""
    batch_id = "test_batch_1"
    _batches[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total_jobs": 2,
        "completed": 0,
        "failed": 0,
        "matrix": [
            {"job_id": "j1", "status": "pending"},
            {"job_id": "j2", "status": "pending"},
        ],
    }
    try:
        _update_batch_job_status(batch_id, "j1", "completed")
        assert _batches[batch_id]["matrix"][0]["status"] == "completed"
        assert _batches[batch_id]["completed"] == 1
        assert _batches[batch_id]["failed"] == 0
        assert _batches[batch_id]["status"] == "running"
    finally:
        _cleanup_batch(batch_id)


def test_update_status_all_completed():
    """全部完成 → batch.status = completed"""
    batch_id = "test_batch_2"
    _batches[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total_jobs": 2,
        "completed": 0,
        "failed": 0,
        "matrix": [
            {"job_id": "j1", "status": "pending"},
            {"job_id": "j2", "status": "pending"},
        ],
    }
    try:
        _update_batch_job_status(batch_id, "j1", "completed")
        _update_batch_job_status(batch_id, "j2", "completed")
        assert _batches[batch_id]["status"] == "completed"
        assert _batches[batch_id]["completed"] == 2
    finally:
        _cleanup_batch(batch_id)


def test_update_status_partial_failure():
    """部分成功部分失败 → batch.status = partial"""
    batch_id = "test_batch_3"
    _batches[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total_jobs": 3,
        "completed": 0,
        "failed": 0,
        "matrix": [
            {"job_id": "j1", "status": "pending"},
            {"job_id": "j2", "status": "pending"},
            {"job_id": "j3", "status": "pending"},
        ],
    }
    try:
        _update_batch_job_status(batch_id, "j1", "completed")
        _update_batch_job_status(batch_id, "j2", "failed")
        assert _batches[batch_id]["status"] == "running"
        _update_batch_job_status(batch_id, "j3", "completed")
        assert _batches[batch_id]["status"] == "partial"
        assert _batches[batch_id]["completed"] == 2
        assert _batches[batch_id]["failed"] == 1
    finally:
        _cleanup_batch(batch_id)


def test_update_status_all_failed():
    """全部失败 → batch.status = failed"""
    batch_id = "test_batch_4"
    _batches[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total_jobs": 2,
        "completed": 0,
        "failed": 0,
        "matrix": [
            {"job_id": "j1", "status": "pending"},
            {"job_id": "j2", "status": "pending"},
        ],
    }
    try:
        _update_batch_job_status(batch_id, "j1", "failed")
        _update_batch_job_status(batch_id, "j2", "failed")
        assert _batches[batch_id]["status"] == "failed"
        assert _batches[batch_id]["failed"] == 2
    finally:
        _cleanup_batch(batch_id)


def test_update_status_nonexistent_batch():
    """更新不存在的 batch（不应抛异常）"""
    _update_batch_job_status("nonexistent", "j1", "completed")


# ======================== _expand_batch_matrix 请求校验 ========================


@pytest.mark.asyncio
async def test_expand_nonexistent_spec_raises(tdb_with_spec):
    """规格书不存在 → 400"""
    tdb, _ = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id="nonexistent",
            character_template_ids=["preset_warrior"],
            action_template_ids=["preset_walk"],
        )
        with pytest.raises(HTTPException, match="规格书不存在"):
            await _expand_batch_matrix(req)
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_expand_nonexistent_character_raises(tdb_with_spec):
    """角色模板不存在 → 400"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=["nonexistent"],
            action_template_ids=["preset_walk"],
        )
        with pytest.raises(HTTPException, match="角色模板不存在"):
            await _expand_batch_matrix(req)
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_expand_nonexistent_action_raises(tdb_with_spec):
    """动作模板不存在 → 400"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=["preset_warrior"],
            action_template_ids=["nonexistent"],
        )
        with pytest.raises(HTTPException, match="动作模板不存在"):
            await _expand_batch_matrix(req)
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_expand_empty_characters_raises(tdb_with_spec):
    """空角色列表 → 400"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=[],
            action_template_ids=["preset_walk"],
        )
        with pytest.raises(HTTPException, match="至少需要一个角色模板"):
            await _expand_batch_matrix(req)
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_expand_empty_actions_raises(tdb_with_spec):
    """空动作列表 → 400"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=["preset_warrior"],
            action_template_ids=[],
        )
        with pytest.raises(HTTPException, match="至少需要一个动作模板"):
            await _expand_batch_matrix(req)
    finally:
        await _restore_tdb(old)


# ======================== _expand_batch_matrix 矩阵展开 ========================


@pytest.mark.asyncio
async def test_expand_matrix_size(tdb_with_spec):
    """3 角色 × 2 动作 = 6 entries"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=["preset_warrior", "preset_mage"],
            action_template_ids=["preset_walk", "preset_idle", "preset_run"],
        )
        entries, spec = await _expand_batch_matrix(req)

        assert len(entries) == 6  # 2 chars × 3 actions
        assert spec is not None
        assert spec.name == "16-bit RPG Chibi"

        chars_found = {e["char"].id for e in entries}
        actions_found = {e["action"].id for e in entries}
        assert "preset_warrior" in chars_found
        assert "preset_mage" in chars_found
        assert "preset_walk" in actions_found
        assert "preset_idle" in actions_found
        assert "preset_run" in actions_found
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_expand_matrix_order(tdb_with_spec):
    """矩阵展开顺序：固定 char 递增 action（先角色后动作）"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=["preset_warrior", "preset_mage"],
            action_template_ids=["preset_idle", "preset_walk"],
        )
        entries, _ = await _expand_batch_matrix(req)

        # 预期顺序：warrior+idle, warrior+walk, mage+idle, mage+walk
        expected = [
            ("preset_warrior", "preset_idle"),
            ("preset_warrior", "preset_walk"),
            ("preset_mage", "preset_idle"),
            ("preset_mage", "preset_walk"),
        ]
        for i, (char_id, action_id) in enumerate(expected):
            assert entries[i]["char"].id == char_id
            assert entries[i]["action"].id == action_id
    finally:
        await _restore_tdb(old)


@pytest.mark.asyncio
async def test_expand_single_char_single_action(tdb_with_spec):
    """单个角色 × 单个动作 → 1 entry"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=["preset_warrior"],
            action_template_ids=["preset_walk"],
        )
        entries, spec = await _expand_batch_matrix(req)

        assert len(entries) == 1
        assert entries[0]["char"].id == "preset_warrior"
        assert entries[0]["action"].id == "preset_walk"
        assert spec is not None
    finally:
        await _restore_tdb(old)


# ======================== get_batch_status ========================


@pytest.mark.asyncio
async def test_get_batch_status_404():
    """查询不存在的 batch → 404"""
    with pytest.raises(HTTPException, match="批量任务不存在"):
        await get_batch_status("nonexistent_batch")


@pytest.mark.asyncio
async def test_get_batch_status_structure():
    """手动构造 batch 后查询，验证返回结构"""
    batch_id = "test_status_batch"
    _batches[batch_id] = {
        "batch_id": batch_id,
        "status": "running",
        "total_jobs": 2,
        "completed": 1,
        "failed": 0,
        "matrix": [
            {"job_id": "j1", "char_id": "char_a", "char_name": "战士",
             "action_id": "act_x", "action_name": "待机", "status": "completed"},
            {"job_id": "j2", "char_id": "char_a", "char_name": "战士",
             "action_id": "act_y", "action_name": "走路", "status": "running"},
        ],
    }
    try:
        result = await get_batch_status(batch_id)
        assert result["batch_id"] == batch_id
        assert result["total_jobs"] == 2
        assert result["completed"] == 1
        assert result["failed"] == 0
        assert len(result["matrix"]) == 2
    finally:
        _cleanup_batch(batch_id)


# ======================== 幂等性 ========================


@pytest.mark.asyncio
async def test_expand_matrix_is_deterministic(tdb_with_spec):
    """相同参数 → 相同矩阵顺序（确定性）"""
    tdb, spec_id = tdb_with_spec
    old = await _inject_tdb(tdb)
    try:
        req = BatchGenerateRequest(
            spec_id=spec_id,
            character_template_ids=["preset_warrior", "preset_mage"],
            action_template_ids=["preset_walk", "preset_idle"],
        )
        e1, _ = await _expand_batch_matrix(req)
        e2, _ = await _expand_batch_matrix(req)

        for i in range(len(e1)):
            assert e1[i]["char"].id == e2[i]["char"].id
            assert e1[i]["action"].id == e2[i]["action"].id
    finally:
        await _restore_tdb(old)


# ======================== BatchGenerateRequest 模型校验 ========================


def test_batch_request_model_defaults():
    """BatchGenerateRequest 默认值"""
    req = BatchGenerateRequest()
    assert req.spec_id == ""
    assert req.character_template_ids == []
    assert req.action_template_ids == []
    assert req.generate_count_per == 4
    assert req.concurrent == 4
    assert req.group_id is None
    assert req.pipeline_id is None
    assert req.vfx_template_ids == []


def test_batch_response_has_generate_count():
    """generate_count_per 默认 4"""
    req = BatchGenerateRequest(
        spec_id="s1",
        character_template_ids=["c1"],
        action_template_ids=["a1"],
        generate_count_per=8,
    )
    assert req.generate_count_per == 8


def test_batch_response_has_concurrent():
    """concurrent 可以自定义"""
    req = BatchGenerateRequest(
        spec_id="s1",
        character_template_ids=["c1"],
        action_template_ids=["a1"],
        concurrent=2,
    )
    assert req.concurrent == 2
