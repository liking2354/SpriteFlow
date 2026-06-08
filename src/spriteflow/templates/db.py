"""模板系统 — SQLite 单表持久层

旧: 6 张表 (sprite_specs / prompt_layers / prompt_blocks
                  / character_templates / action_templates / vfx_templates)
新: 1 张表 prompt_templates
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from ..config import settings
from .models import PromptTemplate, PromptSlot, TemplateType, SlotType


TEMPLATE_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS prompt_templates (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'custom',
    text        TEXT NOT NULL DEFAULT '',
    slots       TEXT DEFAULT '[]',
    description TEXT DEFAULT '',
    tags        TEXT DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pt_type ON prompt_templates(type);
"""


class TemplateDB:
    """模板数据库操作 — 单表 CRUD"""

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

    async def init_tables(self) -> None:
        if not self._conn:
            await self.connect()
        assert self._conn is not None
        await self._conn.executescript(TEMPLATE_SCHEMA_DDL)
        await self._conn.commit()

    # ── 序列化 / 反序列化 ──

    @staticmethod
    def _slots_to_json(slots: list[PromptSlot]) -> str:
        return json.dumps([s.model_dump() for s in slots], ensure_ascii=False)

    @staticmethod
    def _row_to_template(row) -> PromptTemplate:
        slots_raw = json.loads(row["slots"] or "[]")
        return PromptTemplate(
            id=row["id"],
            name=row["name"],
            type=TemplateType(row["type"]),
            text=row["text"] or "",
            slots=[PromptSlot(**s) for s in slots_raw],
            description=row["description"] or "",
            tags=json.loads(row["tags"] or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── CRUD ──

    async def create(self, template: PromptTemplate) -> PromptTemplate:
        assert self._conn is not None
        await self._conn.execute(
            """INSERT OR REPLACE INTO prompt_templates
               (id, name, type, text, slots, description, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (template.id, template.name, template.type.value, template.text,
             self._slots_to_json(template.slots), template.description,
             json.dumps(template.tags, ensure_ascii=False),
             template.created_at, template.updated_at),
        )
        await self._conn.commit()
        return template

    async def list(self, type_filter: str | None = None, limit: int = 200, offset: int = 0) -> list[PromptTemplate]:
        assert self._conn is not None
        sql = "SELECT * FROM prompt_templates"
        params: list = []
        if type_filter:
            sql += " WHERE type = ?"
            params.append(type_filter)
        sql += " ORDER BY type, name LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self._conn.execute_fetchall(sql, params)
        return [self._row_to_template(r) for r in rows]

    async def get(self, template_id: str) -> PromptTemplate | None:
        assert self._conn is not None
        rows = await self._conn.execute_fetchall(
            "SELECT * FROM prompt_templates WHERE id = ?", (template_id,)
        )
        if not rows:
            return None
        return self._row_to_template(rows[0])

    async def update(self, template: PromptTemplate) -> PromptTemplate:
        assert self._conn is not None
        await self._conn.execute(
            """UPDATE prompt_templates SET name=?, type=?, text=?, slots=?,
               description=?, tags=?, updated_at=? WHERE id=?""",
            (template.name, template.type.value, template.text,
             self._slots_to_json(template.slots), template.description,
             json.dumps(template.tags, ensure_ascii=False),
             template.updated_at, template.id),
        )
        await self._conn.commit()
        return template

    async def delete(self, template_id: str) -> None:
        assert self._conn is not None
        await self._conn.execute("DELETE FROM prompt_templates WHERE id = ?", (template_id,))
        await self._conn.commit()

    async def batch_delete(self, template_ids: list[str]) -> int:
        assert self._conn is not None
        placeholders = ",".join("?" for _ in template_ids)
        cursor = await self._conn.execute(
            f"DELETE FROM prompt_templates WHERE id IN ({placeholders})",
            template_ids,
        )
        await self._conn.commit()
        return cursor.rowcount

    async def count(self, type_filter: str | None = None) -> int:
        assert self._conn is not None
        sql = "SELECT COUNT(*) as c FROM prompt_templates"
        params: list = []
        if type_filter:
            sql += " WHERE type = ?"
            params.append(type_filter)
        rows = await self._conn.execute_fetchall(sql, params)
        return rows[0]["c"] if rows else 0
