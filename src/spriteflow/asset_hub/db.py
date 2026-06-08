"""aiosqlite 数据库管理 — Asset + GenerationJob CRUD"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from .models import Asset, AssetGroup, GenerationJob, GraphRun, GraphNodeResult, SCHEMA_DDL
from .video_models import VideoTask, VIDEO_SCHEMA_DDL
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
        await self._conn.executescript(VIDEO_SCHEMA_DDL)
        # 兼容旧表：补列
        await self._add_column_if_missing("assets", "favorite", "INTEGER NOT NULL DEFAULT 0")
        await self._add_column_if_missing("generation_jobs", "parent_id", "TEXT")
        await self._add_column_if_missing("assets", "group_id", "TEXT")
        await self._add_column_if_missing("graph_node_results", "node_type", "TEXT NOT NULL DEFAULT ''")
        await self._add_column_if_missing("graph_node_results", "inputs_json", "TEXT")
        # 在确保列存在后再建索引
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(favorite)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_parent ON generation_jobs(parent_id)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_assets_group ON assets(group_id)"
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
            """INSERT INTO assets (id, type, source, uri, hash, width, height, thumbnail, parent_id, group_id, provenance, favorite, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset.id, asset.type, asset.source, asset.uri, asset.hash,
                asset.width, asset.height, asset.thumbnail, asset.parent_id,
                asset.group_id,
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
        group_id: str | None = None,
        type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Asset], int]:
        assert self._conn is not None
        query_from = "FROM assets a"
        params: list[Any] = []

        where: list[str] = []
        if tags:
            query_from += " JOIN asset_tags at ON a.id = at.asset_id JOIN tags t ON at.tag_id = t.id"
            placeholders = ",".join("?" for _ in tags)
            where.append(f"t.name IN ({placeholders})")
            params.extend(tags)
        if source:
            where.append("a.source = ?")
            params.append(source)
        if favorite is not None:
            where.append("a.favorite = ?")
            params.append(1 if favorite else 0)
        if group_id is not None:
            if group_id == "__none__":
                where.append("a.group_id IS NULL")
            else:
                where.append("a.group_id = ?")
                params.append(group_id)
        if type:
            where.append("a.type = ?")
            params.append(type)

        where_clause = (" WHERE " + " AND ".join(where)) if where else ""

        # 总数
        count_query = f"SELECT COUNT(DISTINCT a.id) {query_from}{where_clause}"
        c = await self._conn.execute(count_query, params.copy())
        row = await c.fetchone()
        total = row[0] if row else 0

        # 分页数据
        data_query = f"SELECT DISTINCT a.* {query_from}{where_clause} ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
        cursor = await self._conn.execute(data_query, [*params, limit, offset])
        rows = await cursor.fetchall()
        assets = [self._row_to_asset(row) for row in rows]
        for asset in assets:
            asset.tags = await self.get_asset_tags(asset.id)
        return assets, total

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

    async def replace_asset_content(
        self,
        asset_id: str,
        *,
        uri: str,
        hash_: str,
        width: int | None,
        height: int | None,
        thumbnail: str | None,
    ) -> bool:
        """覆盖原素材的内容（id/parent_id/tags/favorite 保留）。

        用于"原地编辑"场景：用户在素材编辑器里改完图选择"覆盖原图"。
        """
        assert self._conn is not None
        cursor = await self._conn.execute(
            """
            UPDATE assets
               SET uri = ?, hash = ?, width = ?, height = ?, thumbnail = ?
             WHERE id = ?
            """,
            (uri, hash_, width, height, thumbnail, asset_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def batch_delete_assets(self, asset_ids: list[str]) -> int:
        """批量删除素材，返回删除行数"""
        if not asset_ids:
            return 0
        assert self._conn is not None
        placeholders = ",".join("?" for _ in asset_ids)
        # 先删关联标签
        await self._conn.execute(
            f"DELETE FROM asset_tags WHERE asset_id IN ({placeholders})", tuple(asset_ids)
        )
        cursor = await self._conn.execute(
            f"DELETE FROM assets WHERE id IN ({placeholders})", tuple(asset_ids)
        )
        await self._conn.commit()
        return cursor.rowcount

    async def move_assets_to_group(self, asset_ids: list[str], group_id: str | None) -> int:
        """批量移动素材到指定分组，group_id=None 表示移出分组"""
        if not asset_ids:
            return 0
        assert self._conn is not None
        placeholders = ",".join("?" for _ in asset_ids)
        cursor = await self._conn.execute(
            f"UPDATE assets SET group_id = ? WHERE id IN ({placeholders})",
            (group_id, *asset_ids),
        )
        await self._conn.commit()
        return cursor.rowcount

    # ============================ Group CRUD ============================

    async def create_group(self, group: AssetGroup) -> AssetGroup:
        assert self._conn is not None
        await self._conn.execute(
            "INSERT INTO asset_groups (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (group.id, group.name, group.description, group.created_at),
        )
        await self._conn.commit()
        return group

    async def list_groups(self) -> list[AssetGroup]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT *, (SELECT COUNT(*) FROM assets WHERE group_id = g.id) AS asset_count "
            "FROM asset_groups g ORDER BY g.created_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            AssetGroup(
                id=r["id"], name=r["name"], description=r["description"] or "",
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def get_group(self, group_id: str) -> AssetGroup | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM asset_groups WHERE id = ?", (group_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return AssetGroup(
            id=row["id"], name=row["name"], description=row["description"] or "",
            created_at=row["created_at"],
        )

    async def update_group(self, group_id: str, name: str | None = None, description: str | None = None) -> bool:
        assert self._conn is not None
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = ?"); params.append(name)
        if description is not None:
            sets.append("description = ?"); params.append(description)
        if not sets:
            return False
        params.append(group_id)
        cursor = await self._conn.execute(
            f"UPDATE asset_groups SET {', '.join(sets)} WHERE id = ?", params
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def delete_group(self, group_id: str) -> bool:
        """删除分组（同时将该分组下的素材设为未分组）"""
        assert self._conn is not None
        await self._conn.execute(
            "UPDATE assets SET group_id = NULL WHERE group_id = ?", (group_id,)
        )
        cursor = await self._conn.execute(
            "DELETE FROM asset_groups WHERE id = ?", (group_id,)
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

    # ============================ GraphRun + GraphNodeResult CRUD ============================

    async def create_graph_run(self, run: GraphRun) -> GraphRun:
        assert self._conn is not None
        await self._conn.execute(
            """INSERT INTO graph_runs (id, graph_id, graph_name, graph_json, status,
               started_at, finished_at, summary_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id, run.graph_id, run.graph_name, run.graph_json,
                run.status, run.started_at, run.finished_at, run.summary_json,
                run.created_at,
            ),
        )
        await self._conn.commit()
        return run

    async def update_graph_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        finished_at: str | None = None,
        summary_json: str | None = None,
    ) -> bool:
        assert self._conn is not None
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            sets.append("status = ?"); params.append(status)
        if finished_at is not None:
            sets.append("finished_at = ?"); params.append(finished_at)
        if summary_json is not None:
            sets.append("summary_json = ?"); params.append(summary_json)
        if not sets:
            return False
        params.append(run_id)
        cursor = await self._conn.execute(
            f"UPDATE graph_runs SET {', '.join(sets)} WHERE id = ?", params
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_graph_run(self, run_id: str) -> GraphRun | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM graph_runs WHERE id = ?", (run_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_graph_run(row) if row else None

    async def list_graph_runs(
        self,
        *,
        graph_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[GraphRun], int]:
        assert self._conn is not None
        clauses: list[str] = []
        params: list[Any] = []
        if graph_id is not None:
            clauses.append("graph_id = ?"); params.append(graph_id)
        if status is not None:
            clauses.append("status = ?"); params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        c1 = await self._conn.execute(
            f"SELECT COUNT(*) AS cnt FROM graph_runs {where}", params
        )
        cnt_row = await c1.fetchone()
        total = cnt_row["cnt"] if cnt_row else 0

        c2 = await self._conn.execute(
            f"SELECT * FROM graph_runs {where} "
            f"ORDER BY datetime(created_at) DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        rows = await c2.fetchall()
        return [self._row_to_graph_run(r) for r in rows], total

    async def delete_graph_run(self, run_id: str) -> bool:
        assert self._conn is not None
        # 先删子记录
        await self._conn.execute(
            "DELETE FROM graph_node_results WHERE run_id = ?", (run_id,)
        )
        cursor = await self._conn.execute(
            "DELETE FROM graph_runs WHERE id = ?", (run_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # ── Node Results ──

    async def upsert_node_result(self, nr: GraphNodeResult) -> GraphNodeResult:
        """插入或更新节点执行结果（run_id + node_id 唯一）"""
        assert self._conn is not None
        await self._conn.execute(
            """INSERT INTO graph_node_results
               (run_id, node_id, status, cache_hit, error, asset_id, url, display_url,
                thumbnail_b64, started_at, finished_at, node_type, inputs_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(run_id, node_id) DO UPDATE SET
               status = excluded.status,
               cache_hit = excluded.cache_hit,
               error = excluded.error,
               asset_id = excluded.asset_id,
               url = excluded.url,
               display_url = excluded.display_url,
               thumbnail_b64 = excluded.thumbnail_b64,
               started_at = excluded.started_at,
               finished_at = excluded.finished_at,
               node_type = excluded.node_type,
               inputs_json = excluded.inputs_json""",
            (
                nr.run_id, nr.node_id, nr.status,
                1 if nr.cache_hit else 0, nr.error,
                nr.asset_id, nr.url, nr.display_url,
                nr.thumbnail_b64, nr.started_at, nr.finished_at,
                nr.node_type, nr.inputs_json,
            ),
        )
        await self._conn.commit()
        return nr

    async def get_node_results(self, run_id: str) -> list[GraphNodeResult]:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM graph_node_results WHERE run_id = ? ORDER BY id", (run_id,)
        )
        rows = await cursor.fetchall()
        return [self._row_to_graph_node_result(r) for r in rows]

    async def delete_node_results(self, run_id: str) -> int:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "DELETE FROM graph_node_results WHERE run_id = ?", (run_id,)
        )
        await self._conn.commit()
        return cursor.rowcount

    # ── helpers ──

    def _row_to_graph_run(self, row: aiosqlite.Row) -> GraphRun:
        return GraphRun(
            id=row["id"],
            graph_id=row["graph_id"],
            graph_name=row["graph_name"] or "",
            graph_json=row["graph_json"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            summary_json=row["summary_json"],
            created_at=row["created_at"],
        )

    def _row_to_graph_node_result(self, row: aiosqlite.Row) -> GraphNodeResult:
        keys = row.keys()
        return GraphNodeResult(
            run_id=row["run_id"],
            node_id=row["node_id"],
            status=row["status"],
            cache_hit=bool(row["cache_hit"]),
            error=row["error"],
            asset_id=row["asset_id"],
            url=row["url"],
            display_url=row["display_url"],
            thumbnail_b64=row["thumbnail_b64"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            node_type=row["node_type"] if "node_type" in keys else "",
            inputs_json=row["inputs_json"] if "inputs_json" in keys else None,
        )

    # ============================ helpers ============================

    def _row_to_asset(self, row: aiosqlite.Row) -> Asset:
        keys = row.keys()
        favorite = bool(row["favorite"]) if "favorite" in keys else False
        group_id = row["group_id"] if "group_id" in keys else None
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
            group_id=group_id,
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

    # ============================ VideoTask CRUD ============================

    async def create_video_task(self, task: VideoTask) -> VideoTask:
        assert self._conn is not None
        await self._conn.execute(
            """INSERT INTO video_tasks
               (id, provider, provider_task_id, model, mode, prompt, params, inputs,
                status, error, result_asset_id, last_frame_asset_id, usage_tokens,
                created_at, updated_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id, task.provider, task.provider_task_id, task.model, task.mode,
                task.prompt,
                json.dumps(task.params or {}),
                json.dumps(task.inputs or {}),
                task.status, task.error,
                task.result_asset_id, task.last_frame_asset_id,
                task.usage_tokens,
                task.created_at, task.updated_at, task.completed_at,
            ),
        )
        await self._conn.commit()
        return task

    async def update_video_task(
        self,
        task_id: str,
        *,
        provider_task_id: str | None = None,
        status: str | None = None,
        error: str | None = None,
        result_asset_id: str | None = None,
        last_frame_asset_id: str | None = None,
        usage_tokens: int | None = None,
        updated_at: str | None = None,
        completed_at: str | None = None,
    ) -> bool:
        assert self._conn is not None
        sets: list[str] = []
        params: list[Any] = []
        if provider_task_id is not None:
            sets.append("provider_task_id = ?"); params.append(provider_task_id)
        if status is not None:
            sets.append("status = ?"); params.append(status)
        if error is not None:
            sets.append("error = ?"); params.append(error)
        if result_asset_id is not None:
            sets.append("result_asset_id = ?"); params.append(result_asset_id)
        if last_frame_asset_id is not None:
            sets.append("last_frame_asset_id = ?"); params.append(last_frame_asset_id)
        if usage_tokens is not None:
            sets.append("usage_tokens = ?"); params.append(usage_tokens)
        if updated_at is not None:
            sets.append("updated_at = ?"); params.append(updated_at)
        if completed_at is not None:
            sets.append("completed_at = ?"); params.append(completed_at)
        if not sets:
            return False
        params.append(task_id)
        cursor = await self._conn.execute(
            f"UPDATE video_tasks SET {', '.join(sets)} WHERE id = ?", params
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_video_task(self, task_id: str) -> VideoTask | None:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM video_tasks WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_video_task(row) if row else None

    async def list_video_tasks(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[VideoTask], int]:
        assert self._conn is not None
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        c1 = await self._conn.execute(
            f"SELECT COUNT(*) AS cnt FROM video_tasks {where}", params
        )
        cnt_row = await c1.fetchone()
        total = cnt_row["cnt"] if cnt_row else 0

        c2 = await self._conn.execute(
            f"SELECT * FROM video_tasks {where} "
            f"ORDER BY datetime(created_at) DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        rows = await c2.fetchall()
        return [self._row_to_video_task(r) for r in rows], total

    async def list_unsettled_video_tasks(self) -> list[VideoTask]:
        """返回所有 queued / running 状态的任务（供 worker 轮询）。"""
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM video_tasks WHERE status IN ('queued', 'running') "
            "ORDER BY datetime(created_at) ASC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_video_task(r) for r in rows]

    async def delete_video_task(self, task_id: str) -> bool:
        assert self._conn is not None
        cursor = await self._conn.execute(
            "DELETE FROM video_tasks WHERE id = ?", (task_id,)
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_video_task(self, row: aiosqlite.Row) -> VideoTask:
        def _j(field: str, default: Any) -> Any:
            v = row[field]
            if not v:
                return default
            try:
                return json.loads(v)
            except Exception:
                return default

        return VideoTask(
            id=row["id"],
            provider=row["provider"],
            provider_task_id=row["provider_task_id"],
            model=row["model"],
            mode=row["mode"],
            prompt=row["prompt"] or "",
            params=_j("params", {}),
            inputs=_j("inputs", {}),
            status=row["status"],
            error=row["error"],
            result_asset_id=row["result_asset_id"],
            last_frame_asset_id=row["last_frame_asset_id"],
            usage_tokens=row["usage_tokens"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    # ============================ 运行时配置 ============================

    async def get_config(self, key: str) -> str | None:
        """读取单个配置项"""
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT value FROM configs WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def set_config(self, key: str, value: str) -> None:
        """写入/更新单个配置项"""
        assert self._conn is not None
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await self._conn.execute(
            "INSERT OR REPLACE INTO configs (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        await self._conn.commit()

    async def get_configs_by_prefix(self, prefix: str) -> dict[str, str]:
        """读取指定前缀的所有配置项，去前缀返回"""
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT key, value FROM configs WHERE key LIKE ?", (f"{prefix}%",)
        )
        rows = await cursor.fetchall()
        return {row["key"][len(prefix):]: row["value"] for row in rows}

    async def set_configs_batch(self, items: dict[str, str]) -> None:
        """批量写入配置"""
        assert self._conn is not None
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        for key, value in items.items():
            await self._conn.execute(
                "INSERT OR REPLACE INTO configs (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
        await self._conn.commit()

    async def delete_config(self, key: str) -> None:
        """删除单个配置项"""
        assert self._conn is not None
        await self._conn.execute("DELETE FROM configs WHERE key = ?", (key,))
        await self._conn.commit()
