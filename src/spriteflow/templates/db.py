"""模板系统 — SQLite 数据库层 + Prompt 拼装引擎"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from ..config import settings
from .models import (
    PromptLayer, PromptBlock, CharacterTemplate, ActionTemplate,
    VFXTemplate, SpriteSpec, StagePipeline, StageDef, CanvasSpec, AlignRule,
    PromptAssembly, PromptAssemblyResult, PromptLayerInfo, BlockInfo,
    LayerCategory, BlockCategory,
)


# ============================ DDL ============================

TEMPLATE_SCHEMA_DDL = """
-- 规格书
CREATE TABLE IF NOT EXISTS sprite_specs (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    canvas          TEXT,               -- JSON: CanvasSpec
    align           TEXT,               -- JSON: AlignRule
    default_format  TEXT DEFAULT 'godot',
    default_group_id TEXT,
    version         INTEGER DEFAULT 1,
    is_active       INTEGER DEFAULT 1,
    tags            TEXT DEFAULT '[]',  -- JSON list
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 规格书关联的图层
CREATE TABLE IF NOT EXISTS sprite_spec_layers (
    spec_id     TEXT REFERENCES sprite_specs(id) ON DELETE CASCADE,
    layer_id    TEXT REFERENCES prompt_layers(id) ON DELETE CASCADE,
    sort_order  INTEGER DEFAULT 0,
    PRIMARY KEY (spec_id, layer_id)
);

-- Prompt 图层
CREATE TABLE IF NOT EXISTS prompt_layers (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT DEFAULT 'custom',
    description     TEXT DEFAULT '',
    sort_order      INTEGER DEFAULT 0,
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- Prompt 子块
CREATE TABLE IF NOT EXISTS prompt_blocks (
    id          TEXT PRIMARY KEY,
    layer_id    TEXT REFERENCES prompt_layers(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    content     TEXT NOT NULL,
    category    TEXT DEFAULT 'custom',
    description TEXT DEFAULT '',
    sort_order  INTEGER DEFAULT 0,
    enabled     INTEGER DEFAULT 1,
    tags        TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 角色定义模板
CREATE TABLE IF NOT EXISTS character_templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    key             TEXT NOT NULL UNIQUE,
    description     TEXT NOT NULL,
    color_scheme    TEXT DEFAULT '[]',
    build_type      TEXT DEFAULT '',
    class_type      TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 动作定义模板
CREATE TABLE IF NOT EXISTS action_templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    key             TEXT NOT NULL UNIQUE,
    action_type     TEXT DEFAULT 'idle',
    prompt          TEXT NOT NULL,
    directions      INTEGER DEFAULT 4,
    frames_per_direction INTEGER DEFAULT 4,
    total_frames    INTEGER DEFAULT 16,
    description     TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 技能特效模板
CREATE TABLE IF NOT EXISTS vfx_templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    key             TEXT NOT NULL UNIQUE,
    vfx_type        TEXT DEFAULT 'projectile',
    prompt          TEXT NOT NULL,
    frames          INTEGER DEFAULT 8,
    canvas_width    INTEGER DEFAULT 128,
    canvas_height   INTEGER DEFAULT 128,
    description     TEXT DEFAULT '',
    tags            TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 阶段管线模板
CREATE TABLE IF NOT EXISTS stage_pipelines (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    spec_id         TEXT,
    stages          TEXT DEFAULT '[]',  -- JSON: list[StageDef]
    pause_at_stages TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pb_layer ON prompt_blocks(layer_id);
CREATE INDEX IF NOT EXISTS idx_ct_key ON character_templates(key);
CREATE INDEX IF NOT EXISTS idx_at_key ON action_templates(key);
CREATE INDEX IF NOT EXISTS idx_vt_key ON vfx_templates(key);
"""


# ============================ 数据库操作 ============================

class TemplateDB:
    """模板系统数据库操作 — 与 AssetDB 共享同一个 SQLite 文件"""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else settings.database_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ---- Init ----

    async def init_tables(self) -> None:
        if not self._conn:
            await self.connect()
        assert self._conn is not None
        await self._conn.executescript(TEMPLATE_SCHEMA_DDL)
        await self._conn.commit()

    # ======================== PromptLayer ========================

    async def create_layer(self, layer: PromptLayer) -> PromptLayer:
        await self._conn.execute(
            """INSERT OR REPLACE INTO prompt_layers (id, name, category, description, sort_order, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (layer.id, layer.name, layer.category.value, layer.description,
             layer.sort_order, int(layer.enabled), layer.created_at, layer.updated_at),
        )
        await self._conn.commit()
        return layer

    async def list_layers(self, category: str | None = None) -> list[PromptLayer]:
        sql = "SELECT * FROM prompt_layers"
        params: list = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY sort_order"
        rows = await self._conn.execute_fetchall(sql, params)
        out: list[PromptLayer] = []
        for r in rows:
            blocks = await self._list_blocks_by_layer(r["id"])
            out.append(PromptLayer(
                id=r["id"], name=r["name"],
                category=LayerCategory(r["category"]),
                description=r["description"] or "",
                blocks=blocks,
                sort_order=r["sort_order"],
                enabled=bool(r["enabled"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            ))
        return out

    async def get_layer(self, layer_id: str) -> PromptLayer | None:
        r = await self._conn.execute_fetchall("SELECT * FROM prompt_layers WHERE id = ?", (layer_id,))
        if not r:
            return None
        row = r[0]
        blocks = await self._list_blocks_by_layer(layer_id)
        return PromptLayer(
            id=row["id"], name=row["name"],
            category=LayerCategory(row["category"]),
            description=row["description"] or "",
            blocks=blocks,
            sort_order=row["sort_order"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    async def update_layer(self, layer: PromptLayer) -> None:
        await self._conn.execute(
            """UPDATE prompt_layers SET name=?, category=?, description=?, sort_order=?, enabled=?, updated_at=?
               WHERE id=?""",
            (layer.name, layer.category.value, layer.description,
             layer.sort_order, int(layer.enabled), layer.updated_at, layer.id),
        )
        await self._conn.commit()

    async def delete_layer(self, layer_id: str) -> None:
        await self._conn.execute("DELETE FROM prompt_layers WHERE id = ?", (layer_id,))
        await self._conn.commit()

    # ---- Blocks ----

    async def _list_blocks_by_layer(self, layer_id: str) -> list[PromptBlock]:
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM prompt_blocks WHERE layer_id = ? ORDER BY sort_order", (layer_id,)
        )
        return [
            PromptBlock(
                id=r["id"], name=r["name"], content=r["content"],
                category=BlockCategory(r["category"]),
                description=r["description"] or "",
                sort_order=r["sort_order"], enabled=bool(r["enabled"]),
                tags=json.loads(r["tags"] or "[]"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def create_block(self, block: PromptBlock, layer_id: str) -> PromptBlock:
        await self._conn.execute(
            """INSERT OR REPLACE INTO prompt_blocks (id, layer_id, name, content, category, description, sort_order, enabled, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (block.id, layer_id, block.name, block.content, block.category.value,
             block.description, block.sort_order, int(block.enabled),
             json.dumps(block.tags, ensure_ascii=False),
             block.created_at, block.updated_at),
        )
        await self._conn.commit()
        return block

    async def update_block(self, block: PromptBlock) -> None:
        await self._conn.execute(
            """UPDATE prompt_blocks SET name=?, content=?, category=?, description=?, sort_order=?, enabled=?, tags=?, updated_at=?
               WHERE id=?""",
            (block.name, block.content, block.category.value, block.description,
             block.sort_order, int(block.enabled),
             json.dumps(block.tags, ensure_ascii=False),
             block.updated_at, block.id),
        )
        await self._conn.commit()

    async def delete_block(self, block_id: str) -> None:
        await self._conn.execute("DELETE FROM prompt_blocks WHERE id = ?", (block_id,))
        await self._conn.commit()

    # ======================== SpriteSpec ========================

    async def create_spec(self, spec: SpriteSpec) -> SpriteSpec:
        await self._conn.execute(
            """INSERT OR REPLACE INTO sprite_specs (id, name, description, canvas, align, default_format, default_group_id, version, is_active, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (spec.id, spec.name, spec.description,
             spec.canvas.model_dump_json(), spec.align.model_dump_json(),
             spec.default_format.value, spec.default_group_id,
             spec.version, int(spec.is_active),
             json.dumps(spec.tags, ensure_ascii=False),
             spec.created_at, spec.updated_at),
        )
        # 关联图层
        for i, layer in enumerate(spec.layers):
            await self._conn.execute(
                "INSERT OR REPLACE INTO sprite_spec_layers (spec_id, layer_id, sort_order) VALUES (?, ?, ?)",
                (spec.id, layer.id, i),
            )
        await self._conn.commit()
        return spec

    async def get_spec(self, spec_id: str) -> SpriteSpec | None:
        rows = await self._conn.execute_fetchall("SELECT * FROM sprite_specs WHERE id = ?", (spec_id,))
        if not rows:
            return None
        r = rows[0]
        layers = await self._list_spec_layers(spec_id)
        return SpriteSpec(
            id=r["id"], name=r["name"], description=r["description"] or "",
            canvas=CanvasSpec.model_validate_json(r["canvas"] or "{}"),
            align=AlignRule.model_validate_json(r["align"] or "{}"),
            layers=layers,
            default_format=r["default_format"] or "godot",
            default_group_id=r["default_group_id"],
            version=r["version"], is_active=bool(r["is_active"]),
            tags=json.loads(r["tags"] or "[]"),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    async def list_specs(self) -> list[SpriteSpec]:
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM sprite_specs ORDER BY is_active DESC, created_at DESC"
        )
        out = []
        for r in rows:
            layers = await self._list_spec_layers(r["id"])
            out.append(SpriteSpec(
                id=r["id"], name=r["name"], description=r["description"] or "",
                canvas=CanvasSpec.model_validate_json(r["canvas"] or "{}"),
                align=AlignRule.model_validate_json(r["align"] or "{}"),
                layers=layers,
                default_format=r["default_format"] or "godot",
                default_group_id=r["default_group_id"],
                version=r["version"], is_active=bool(r["is_active"]),
                tags=json.loads(r["tags"] or "[]"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            ))
        return out

    async def update_spec(self, spec: SpriteSpec) -> None:
        await self._conn.execute(
            """UPDATE sprite_specs SET name=?, description=?, canvas=?, align=?, default_format=?, default_group_id=?, version=?, is_active=?, tags=?, updated_at=?
               WHERE id=?""",
            (spec.name, spec.description,
             spec.canvas.model_dump_json(), spec.align.model_dump_json(),
             spec.default_format.value, spec.default_group_id,
             spec.version, int(spec.is_active),
             json.dumps(spec.tags, ensure_ascii=False),
             spec.updated_at, spec.id),
        )
        await self._conn.execute("DELETE FROM sprite_spec_layers WHERE spec_id = ?", (spec.id,))
        for i, layer in enumerate(spec.layers):
            await self._conn.execute(
                "INSERT INTO sprite_spec_layers (spec_id, layer_id, sort_order) VALUES (?, ?, ?)",
                (spec.id, layer.id, i),
            )
        await self._conn.commit()

    async def delete_spec(self, spec_id: str) -> None:
        await self._conn.execute("DELETE FROM sprite_specs WHERE id = ?", (spec_id,))
        await self._conn.commit()

    async def _list_spec_layers(self, spec_id: str) -> list[PromptLayer]:
        rows = await self._conn.execute_fetchall(
            "SELECT pl.* FROM prompt_layers pl "
            "JOIN sprite_spec_layers ssl ON pl.id = ssl.layer_id "
            "WHERE ssl.spec_id = ? ORDER BY ssl.sort_order",
            (spec_id,)
        )
        out = []
        for r in rows:
            blocks = await self._list_blocks_by_layer(r["id"])
            out.append(PromptLayer(
                id=r["id"], name=r["name"],
                category=LayerCategory(r["category"]),
                description=r["description"] or "",
                blocks=blocks,
                sort_order=r["sort_order"],
                enabled=bool(r["enabled"]),
                created_at=r["created_at"], updated_at=r["updated_at"],
            ))
        return out

    # ======================== CharacterTemplate ========================

    async def create_character(self, ct: CharacterTemplate) -> CharacterTemplate:
        await self._conn.execute(
            """INSERT OR REPLACE INTO character_templates (id, name, key, description, color_scheme, build_type, class_type, tags, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ct.id, ct.name, ct.key, ct.description,
             json.dumps(ct.color_scheme, ensure_ascii=False), ct.build_type, ct.class_type,
             json.dumps(ct.tags, ensure_ascii=False),
             json.dumps(ct.metadata, ensure_ascii=False),
             ct.created_at, ct.updated_at),
        )
        await self._conn.commit()
        return ct

    async def list_characters(self, class_type: str | None = None) -> list[CharacterTemplate]:
        sql = "SELECT * FROM character_templates"
        params: list = []
        if class_type:
            sql += " WHERE class_type = ?"
            params.append(class_type)
        sql += " ORDER BY class_type, name"
        rows = await self._conn.execute_fetchall(sql, params)
        return [
            CharacterTemplate(
                id=r["id"], name=r["name"], key=r["key"],
                description=r["description"],
                color_scheme=json.loads(r["color_scheme"] or "[]"),
                build_type=r["build_type"] or "", class_type=r["class_type"] or "",
                tags=json.loads(r["tags"] or "[]"),
                metadata=json.loads(r["metadata"] or "{}"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def get_character(self, char_id: str) -> CharacterTemplate | None:
        rows = await self._conn.execute_fetchall("SELECT * FROM character_templates WHERE id = ?", (char_id,))
        if not rows:
            return None
        r = rows[0]
        return CharacterTemplate(
            id=r["id"], name=r["name"], key=r["key"],
            description=r["description"],
            color_scheme=json.loads(r["color_scheme"] or "[]"),
            build_type=r["build_type"] or "", class_type=r["class_type"] or "",
            tags=json.loads(r["tags"] or "[]"),
            metadata=json.loads(r["metadata"] or "{}"),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    async def update_character(self, ct: CharacterTemplate) -> None:
        await self._conn.execute(
            """UPDATE character_templates SET name=?, key=?, description=?, color_scheme=?, build_type=?, class_type=?, tags=?, metadata=?, updated_at=?
               WHERE id=?""",
            (ct.name, ct.key, ct.description,
             json.dumps(ct.color_scheme, ensure_ascii=False), ct.build_type, ct.class_type,
             json.dumps(ct.tags, ensure_ascii=False),
             json.dumps(ct.metadata, ensure_ascii=False),
             ct.updated_at, ct.id),
        )
        await self._conn.commit()

    async def delete_character(self, char_id: str) -> None:
        await self._conn.execute("DELETE FROM character_templates WHERE id = ?", (char_id,))
        await self._conn.commit()

    # ======================== ActionTemplate ========================

    async def create_action(self, at: ActionTemplate) -> ActionTemplate:
        await self._conn.execute(
            """INSERT OR REPLACE INTO action_templates (id, name, key, action_type, prompt, directions, frames_per_direction, total_frames, description, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (at.id, at.name, at.key, at.action_type.value, at.prompt,
             at.directions, at.frames_per_direction, at.total_frames,
             at.description, json.dumps(at.tags, ensure_ascii=False),
             at.created_at, at.updated_at),
        )
        await self._conn.commit()
        return at

    async def list_actions(self) -> list[ActionTemplate]:
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM action_templates ORDER BY action_type, name"
        )
        from .models import ActionType
        return [
            ActionTemplate(
                id=r["id"], name=r["name"], key=r["key"],
                action_type=ActionType(r["action_type"]),
                prompt=r["prompt"],
                directions=r["directions"], frames_per_direction=r["frames_per_direction"],
                total_frames=r["total_frames"], description=r["description"] or "",
                tags=json.loads(r["tags"] or "[]"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def get_action(self, action_id: str) -> ActionTemplate | None:
        rows = await self._conn.execute_fetchall("SELECT * FROM action_templates WHERE id = ?", (action_id,))
        if not rows:
            return None
        r = rows[0]
        from .models import ActionType
        return ActionTemplate(
            id=r["id"], name=r["name"], key=r["key"],
            action_type=ActionType(r["action_type"]),
            prompt=r["prompt"],
            directions=r["directions"], frames_per_direction=r["frames_per_direction"],
            total_frames=r["total_frames"], description=r["description"] or "",
            tags=json.loads(r["tags"] or "[]"),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    async def update_action(self, at: ActionTemplate) -> None:
        await self._conn.execute(
            """UPDATE action_templates SET name=?, key=?, action_type=?, prompt=?, directions=?, frames_per_direction=?, total_frames=?, description=?, tags=?, updated_at=?
               WHERE id=?""",
            (at.name, at.key, at.action_type.value, at.prompt,
             at.directions, at.frames_per_direction, at.total_frames,
             at.description, json.dumps(at.tags, ensure_ascii=False),
             at.updated_at, at.id),
        )
        await self._conn.commit()

    async def delete_action(self, action_id: str) -> None:
        await self._conn.execute("DELETE FROM action_templates WHERE id = ?", (action_id,))
        await self._conn.commit()

    # ======================== VFXTemplate ========================

    async def create_vfx(self, vfx: VFXTemplate) -> VFXTemplate:
        await self._conn.execute(
            """INSERT OR REPLACE INTO vfx_templates (id, name, key, vfx_type, prompt, frames, canvas_width, canvas_height, description, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (vfx.id, vfx.name, vfx.key, vfx.vfx_type, vfx.prompt,
             vfx.frames, vfx.canvas_width, vfx.canvas_height,
             vfx.description, json.dumps(vfx.tags, ensure_ascii=False),
             vfx.created_at, vfx.updated_at),
        )
        await self._conn.commit()
        return vfx

    async def list_vfx(self) -> list[VFXTemplate]:
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM vfx_templates ORDER BY vfx_type, name"
        )
        return [
            VFXTemplate(
                id=r["id"], name=r["name"], key=r["key"], vfx_type=r["vfx_type"] or "",
                prompt=r["prompt"], frames=r["frames"],
                canvas_width=r["canvas_width"], canvas_height=r["canvas_height"],
                description=r["description"] or "",
                tags=json.loads(r["tags"] or "[]"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def get_vfx(self, vfx_id: str) -> VFXTemplate | None:
        rows = await self._conn.execute_fetchall("SELECT * FROM vfx_templates WHERE id = ?", (vfx_id,))
        if not rows:
            return None
        r = rows[0]
        return VFXTemplate(
            id=r["id"], name=r["name"], key=r["key"], vfx_type=r["vfx_type"] or "",
            prompt=r["prompt"], frames=r["frames"],
            canvas_width=r["canvas_width"], canvas_height=r["canvas_height"],
            description=r["description"] or "",
            tags=json.loads(r["tags"] or "[]"),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    async def update_vfx(self, vfx: VFXTemplate) -> None:
        await self._conn.execute(
            """UPDATE vfx_templates SET name=?, key=?, vfx_type=?, prompt=?, frames=?, canvas_width=?, canvas_height=?, description=?, tags=?, updated_at=?
               WHERE id=?""",
            (vfx.name, vfx.key, vfx.vfx_type, vfx.prompt,
             vfx.frames, vfx.canvas_width, vfx.canvas_height,
             vfx.description, json.dumps(vfx.tags, ensure_ascii=False),
             vfx.updated_at, vfx.id),
        )
        await self._conn.commit()

    async def delete_vfx(self, vfx_id: str) -> None:
        await self._conn.execute("DELETE FROM vfx_templates WHERE id = ?", (vfx_id,))
        await self._conn.commit()

    # ======================== StagePipeline ========================

    async def create_pipeline(self, pipeline: StagePipeline) -> StagePipeline:
        await self._conn.execute(
            """INSERT OR REPLACE INTO stage_pipelines (id, name, description, spec_id, stages, pause_at_stages, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (pipeline.id, pipeline.name, pipeline.description, pipeline.spec_id,
             json.dumps([s.model_dump() for s in pipeline.stages], ensure_ascii=False),
             json.dumps(pipeline.pause_at_stages, ensure_ascii=False),
             pipeline.created_at, pipeline.updated_at),
        )
        await self._conn.commit()
        return pipeline

    async def list_pipelines(self) -> list[StagePipeline]:
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM stage_pipelines ORDER BY created_at DESC"
        )
        return [
            StagePipeline(
                id=r["id"], name=r["name"], description=r["description"] or "",
                spec_id=r["spec_id"] or "",
                stages=[StageDef(**s) for s in json.loads(r["stages"] or "[]")],
                pause_at_stages=json.loads(r["pause_at_stages"] or "[]"),
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    async def get_pipeline(self, pipeline_id: str) -> StagePipeline | None:
        rows = await self._conn.execute_fetchall("SELECT * FROM stage_pipelines WHERE id = ?", (pipeline_id,))
        if not rows:
            return None
        r = rows[0]
        return StagePipeline(
            id=r["id"], name=r["name"], description=r["description"] or "",
            spec_id=r["spec_id"] or "",
            stages=[StageDef(**s) for s in json.loads(r["stages"] or "[]")],
            pause_at_stages=json.loads(r["pause_at_stages"] or "[]"),
            created_at=r["created_at"], updated_at=r["updated_at"],
        )

    async def delete_pipeline(self, pipeline_id: str) -> None:
        await self._conn.execute("DELETE FROM stage_pipelines WHERE id = ?", (pipeline_id,))
        await self._conn.commit()
