"""aiosqlite 数据库管理 — Asset + GenerationJob CRUD"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from .models import Asset, GenerationJob, SCHEMA_DDL
from ..config import settings


class AssetDB:
    """素材 + 任务元数据数据库"""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else settings.database_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(str(self.db_path))
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
        await self._conn.executescript(SCHEMA_DDL)
        # 兼容旧表：补 favorite 列（如果不存在）
        await self._add_column_if_missing("assets", "favorite", "INTEGER NOT NULL DEFAULT 0")
        await self._add_column_if_missing("generation_jobs", "parent_id", "TEXT")
        # 在确保列存在后再建索引
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(favorite)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_parent ON generation_jobs(parent_id)"
        )
        await self._conn.commit()

    async def _add_column_if_missing(self, table: str, column: str, ddl_type: str) -> None:
        assert self._conn is not None
        cursor = await self._conn.execute(f"PRAGMA table_info({table})")
        cols = [r["name"] for r in await cursor.fetchall()]
        if column not in cols:
            try:
                await self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
            except Exception:
                pass

    # ============================ Asset CRUD ============================

    async def create_asset(self, asset: Asset) -> Asset:
        assert self._conn is not None
        await self._conn.execute(
            """INSERT INTO assets (id, type, source, uri, hash, width, height, thumbnail, parent_id, provenance, favorite, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset.id, asset.type, asset.source, asset.uri, asset.hash,
                asset.width, asset.height, asset.thumbnail, asset.parent_id,
                json.dumps(asset.provenance) if asset.provenance else None,
                1 if asset.favorite else 0,
                asset.created_at,
            ),
        )
        for tag_name in asset.tags:
            await self._ensure_tag(tag_name)
            tag_id = await self._get_tag_id(tag_name)
            if tag_id is not None:
                await self._conn.execute(
                    "INSERT OR IGNORE INTO asset_tags (asset_id, tag_id) VALUES (?, ?)",
                    (asset.id, tag_id),
                )
        await self._conn.commit()
        return asset

    async def get_asset(self, asset_id: str) -> Asset | None:
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        asset = self._row_to_asset(row)
        asset.tags = await self.get_asset_tags(asset_id)
        return asset

    async def get_assets_by_ids(self, ids: list[str]) -> list[Asset]:
        if not ids:
            return []
        assert self._conn is not None
        placeholders = ",".join("?" for _ in ids)
        cursor = await self._conn.execute(
            f"SELECT * FROM assets WHERE id IN ({placeholders})", tuple(ids)
        )
        rows = await cursor.fetchall()
        # 保持原顺序
        index = {r["id"]: r for r in rows}
        out: list[Asset] = []
        for i in ids:
            r = index.get(i)
            if r is None:
                continue
            a = self._row_to_asset(r)
            a.tags = await self.get_asset_tags(a.id)
            out.append(a)
        return out

    async def get_asset_by_hash(self, content_hash: str) -> Asset | None:
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT * FROM assets WHERE hash = ?", (content_hash,))
        row = await cursor.fetchone()
        if not row:
            return None
        asset = self._row_to_asset(row)
        asset.tags = await self.get_asset_tags(asset.id)
        return asset

    async def list_assets(
        self,
        source: str | None = None,
        tags: list[str] | None = None,
        favorite: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Asset]:
        assert self._conn is not None
        query = "SELECT DISTINCT a.* FROM assets a"
        params: list[Any] = []

        where: list[str] = []
        if tags:
            query += " JOIN asset_tags at ON a.id = at.asset_id JOIN tags t ON at.tag_id = t.id"
            placeholders = ",".join("?" for _ in tags)
            where.append(f"t.name IN ({placeholders})")
            params.extend(tags)
        if source:
            where.append("a.source = ?")
            params.append(source)
        if favorite is not None:
            where.append("a.favorite = ?")
            params.append(1 if favorite else 0)

        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        assets = [self._row_to_asset(row) for row in rows]
        for asset in assets:
            asset.tags = await self.get_asset_tags(asset.id)
        return assets

    async def get_children(self, parent_id: str) -> list[Asset]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM assets WHERE parent_id = ? ORDER BY created_at",
            (parent_id,),
        )
        rows = await cursor.fetchall()
        assets = [self._row_to_asset(row) for row in rows]
        for asset in assets:
            asset.tags = await self.get_asset_tags(asset.id)
        return assets

    async def delete_asset(self, asset_id: str) -> bool:
        assert self._conn is not None
        await self._conn.execute("DELETE FROM asset_tags WHERE asset_id = ?", (asset_id,))
        cursor = await self._conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def set_asset_favorite(self, asset_id: str, favorite: bool) -> bool:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "UPDATE assets SET favorite = ? WHERE id = ?",
            (1 if favorite else 0, asset_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ============================ Tag helpers ============================

    async def _ensure_tag(self, name: str) -> None:
        assert self._conn is not None
        await self._conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))

    async def _get_tag_id(self, name: str) -> int | None:
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT id FROM tags WHERE name = ?", (name,))
        row = await cursor.fetchone()
        return row["id"] if row else None

    async def get_tags(self) -> list[str]:
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT name FROM tags ORDER BY name")
        rows = await cursor.fetchall()
        return [row["name"] for row in rows]

    async def get_asset_tags(self, asset_id: str) -> list[str]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            """SELECT t.name FROM tags t
               JOIN asset_tags at ON t.id = at.tag_id
               WHERE at.asset_id = ?""",
            (asset_id,),
        )
        rows = await cursor.fetchall()
        return [row["name"] for row in rows]

    # ============================ GenerationJob CRUD ============================

    async def create_job(self, job: GenerationJob) -> GenerationJob:
        assert self._conn is not None
        await self._conn.execute(
            """INSERT INTO generation_jobs
               (id, mode, prompt, params, ref_image_urls, ref_asset_ids, asset_ids, status,
                error, favorite, model, usage, parent_id, created_at, finished_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job.id, job.mode, job.prompt,
                json.dumps(job.params or {}),
                json.dumps(job.ref_image_urls or []),
                json.dumps(job.ref_asset_ids or []),
                json.dumps(job.asset_ids or []),
                job.status,
                job.error,
                1 if job.favorite else 0,
                job.model,
                json.dumps(job.usage) if job.usage else None,
                job.parent_id,
                job.created_at,
                job.finished_at,
            ),
        )
        await self._conn.commit()
        return job

    async def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        asset_ids: list[str] | None = None,
        error: str | None = None,
        model: str | None = None,
        usage: dict | None = None,
        finished_at: str | None = None,
    ) -> bool:
        assert self._conn is not None
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            sets.append("status = ?"); params.append(status)
        if asset_ids is not None:
            sets.append("asset_ids = ?"); params.append(json.dumps(asset_ids))
        if error is not None:
            sets.append("error = ?"); params.append(error)
        if model is not None:
            sets.append("model = ?"); params.append(model)
        if usage is not None:
            sets.append("usage = ?"); params.append(json.dumps(usage))
        if finished_at is not None:
            sets.append("finished_at = ?"); params.append(finished_at)
        if not sets:
            return False
        params.append(job_id)
        cursor = await self._conn.execute(
            f"UPDATE generation_jobs SET {', '.join(sets)} WHERE id = ?", params
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def set_job_favorite(self, job_id: str, favorite: bool) -> bool:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "UPDATE generation_jobs SET favorite = ? WHERE id = ?",
            (1 if favorite else 0, job_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_job(self, job_id: str) -> GenerationJob | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM generation_jobs WHERE id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_job(row) if row else None

    async def list_jobs(
        self,
        favorite: bool | None = None,
        limit: int = 50,
        offset: int = 0,
        only_root: bool = True,
    ) -> tuple[list[GenerationJob], int]:
        assert self._conn is not None
        clauses: list[str] = []
        params: list[Any] = []
        if favorite is not None:
            clauses.append("favorite = ?")
            params.append(1 if favorite else 0)
        if only_root:
            clauses.append("parent_id IS NULL")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        # 总数
        c1 = await self._conn.execute(
            f"SELECT COUNT(*) AS cnt FROM generation_jobs {where}", params
        )
        cnt_row = await c1.fetchone()
        total = cnt_row["cnt"] if cnt_row else 0

        c2 = await self._conn.execute(
            f"SELECT * FROM generation_jobs {where} "
            f"ORDER BY datetime(created_at) DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        rows = await c2.fetchall()
        return [self._row_to_job(r) for r in rows], total

    async def list_children_jobs(self, parent_id: str) -> list[GenerationJob]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM generation_jobs WHERE parent_id = ? "
            "ORDER BY datetime(created_at) ASC, id ASC",
            (parent_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_job(r) for r in rows]

    async def delete_job(self, job_id: str) -> bool:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "DELETE FROM generation_jobs WHERE id = ?", (job_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ============================ helpers ============================

    def _row_to_asset(self, row: aiosqlite.Row) -> Asset:
        keys = row.keys()
        favorite = bool(row["favorite"]) if "favorite" in keys else False
        return Asset(
            id=row["id"],
            type=row["type"],
            source=row["source"],
            uri=row["uri"],
            hash=row["hash"],
            width=row["width"],
            height=row["height"],
            thumbnail=row["thumbnail"],
            parent_id=row["parent_id"],
            provenance=json.loads(row["provenance"]) if row["provenance"] else None,
            favorite=favorite,
            created_at=row["created_at"],
        )

    def _row_to_job(self, row: aiosqlite.Row) -> GenerationJob:
        def _j(field: str, default: Any) -> Any:
            v = row[field]
            if not v:
                return default
            try:
                return json.loads(v)
            except Exception:
                return default
        keys = row.keys()
        parent_id = row["parent_id"] if "parent_id" in keys else None
        return GenerationJob(
            id=row["id"],
            mode=row["mode"],
            prompt=row["prompt"],
            params=_j("params", {}),
            ref_image_urls=_j("ref_image_urls", []),
            ref_asset_ids=_j("ref_asset_ids", []),
            asset_ids=_j("asset_ids", []),
            status=row["status"],
            error=row["error"],
            favorite=bool(row["favorite"]),
            model=row["model"],
            usage=_j("usage", None),
            parent_id=parent_id,
            created_at=row["created_at"],
            finished_at=row["finished_at"],
        )
