"""素材数据模型 + SQLite Schema DDL"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Asset(BaseModel):
    """统一素材模型"""

    id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))
    type: Literal["image", "video", "audio", "text", "spritesheet"] = "image"
    source: Literal["uploaded", "generated", "derived", "ai_processed"] = "uploaded"
    uri: str = ""                     # COS 对象路径
    hash: str = ""                    # 内容哈希（去重 + 缓存寻址）
    width: int | None = None
    height: int | None = None
    thumbnail: str | None = None      # 缩略图 URI
    tags: list[str] = Field(default_factory=list)
    parent_id: str | None = None      # 血缘：上游素材 id
    group_id: str | None = None       # 归属分组
    provenance: dict | None = None    # 生成它的管线 id + 参数快照
    favorite: bool = False             # 是否收藏
    text_preview: str | None = None   # 文本素材预览片段（前200字符）
    duration: float | None = None     # 音视频时长（秒）
    mime_type: str | None = None      # MIME 类型（如 text/plain, audio/mpeg）
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class AssetGroup(BaseModel):
    """素材分组 / 项目"""

    id: str = Field(default_factory=lambda: f"grp_{uuid.uuid4().hex[:12]}")
    name: str
    description: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class Tag(BaseModel):
    """标签"""

    id: int | None = None
    name: str  # "char:knight"


class GenerationJob(BaseModel):
    """生成任务记录 — 一次"创作"完整记录（输入参数 + 输出素材）"""

    id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}")
    mode: str = "text2img"
    prompt: str = ""
    params: dict = Field(default_factory=dict)
    ref_image_urls: list[str] = Field(default_factory=list)
    ref_asset_ids: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    error: str | None = None
    favorite: bool = False
    model: str | None = None
    usage: dict | None = None
    parent_id: str | None = None      # 再次生成时关联到原 job
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str | None = None


class GraphRun(BaseModel):
    """管线图执行记录"""

    id: str = ""
    graph_id: str = ""
    graph_name: str = ""
    graph_json: str | None = None       # JSON string: 完整图快照
    status: str = "pending"              # pending / running / completed / failed
    started_at: str | None = None
    finished_at: str | None = None
    summary_json: str | None = None      # JSON string: _build_run_summary 结果
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class GraphNodeResult(BaseModel):
    """单个节点执行结果"""

    run_id: str = Field(default="", serialization_alias="runId")
    node_id: str = Field(default="", serialization_alias="nodeId")
    status: str = Field(default="pending", serialization_alias="status")  # pending / queued / running / completed / failed
    cache_hit: bool = Field(default=False, serialization_alias="cacheHit")
    error: str | None = Field(default=None, serialization_alias="error")
    asset_id: str | None = Field(default=None, serialization_alias="assetId")
    url: str | None = Field(default=None, serialization_alias="rawUrl")                      # 原始存储 URI（如 cos://...）
    display_url: str | None = Field(default=None, serialization_alias="url")                  # 前端可用的 HTTP URL（由 _resolve_display_url 生成）
    thumbnail_b64: str | None = Field(default=None, serialization_alias="thumbnail")          # base64 缩略图（≤128px，不含 data: 前缀）
    started_at: str | None = Field(default=None, serialization_alias="startedAt")
    finished_at: str | None = Field(default=None, serialization_alias="finishedAt")
    node_type: str = Field(default="", serialization_alias="nodeType")                        # 节点类型（如 direction_variant, text2img）
    inputs_json: str | None = Field(default=None, serialization_alias="inputsJson")            # 执行输入快照 JSON（prompt/params 等）


# ---- SQLite DDL ----

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS assets (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    source      TEXT NOT NULL,
    uri         TEXT NOT NULL,
    hash        TEXT NOT NULL,
    width       INTEGER,
    height      INTEGER,
    thumbnail   TEXT,
    parent_id   TEXT REFERENCES assets(id),
    provenance  TEXT,
    favorite    INTEGER NOT NULL DEFAULT 0,
    group_id    TEXT,
    text_preview TEXT,
    duration    REAL,
    mime_type   TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_hash ON assets(hash);
CREATE INDEX IF NOT EXISTS idx_assets_source ON assets(source);
CREATE INDEX IF NOT EXISTS idx_assets_parent ON assets(parent_id);

CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_tags (
    asset_id  TEXT REFERENCES assets(id) ON DELETE CASCADE,
    tag_id    INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (asset_id, tag_id)
);

-- 创作任务记录
CREATE TABLE IF NOT EXISTS generation_jobs (
    id              TEXT PRIMARY KEY,
    mode            TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    params          TEXT,                 -- JSON
    ref_image_urls  TEXT,                 -- JSON list
    ref_asset_ids   TEXT,                 -- JSON list
    asset_ids       TEXT,                 -- JSON list of asset ids
    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT,
    favorite        INTEGER NOT NULL DEFAULT 0,
    model           TEXT,
    usage           TEXT,                 -- JSON
    parent_id       TEXT,                 -- 再次生成关联的父 job
    created_at      TEXT NOT NULL,
    finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON generation_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_favorite ON generation_jobs(favorite);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON generation_jobs(status);

-- 素材分组（项目）
CREATE TABLE IF NOT EXISTS asset_groups (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

-- 运行时配置（路由、凭证、Provider 参数）
CREATE TABLE IF NOT EXISTS configs (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- ==================== 管线图运行记录 ====================

-- 管线图执行记录（一次 Run）
CREATE TABLE IF NOT EXISTS graph_runs (
    id              TEXT PRIMARY KEY,
    graph_id        TEXT NOT NULL,
    graph_name      TEXT NOT NULL DEFAULT '',
    graph_json      TEXT,                 -- JSON: 完整图快照（PipelineGraphModel），供 rerun/回溯
    status          TEXT NOT NULL DEFAULT 'pending',
    started_at      TEXT,
    finished_at     TEXT,
    summary_json    TEXT,                 -- JSON: { duration, success_count, failed_count, cache_hits, assets, failed_nodes }
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_graph_runs_graph_id ON graph_runs(graph_id);
CREATE INDEX IF NOT EXISTS idx_graph_runs_status ON graph_runs(status);
CREATE INDEX IF NOT EXISTS idx_graph_runs_created ON graph_runs(created_at DESC);

-- 单个节点执行结果
CREATE TABLE IF NOT EXISTS graph_node_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES graph_runs(id) ON DELETE CASCADE,
    node_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    cache_hit       INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    asset_id        TEXT,
    url             TEXT,                 -- 原始存储 URI
    display_url     TEXT,                 -- 前端可用的 HTTP URL
    thumbnail_b64   TEXT,                 -- base64 缩略图（≤128px，约 2-5KB）
    started_at      TEXT,
    finished_at     TEXT,
    node_type       TEXT NOT NULL DEFAULT '',
    inputs_json     TEXT                  -- JSON: 执行输入快照 {prompt, template_ids, slot_values, variants, params, ...}
);
CREATE INDEX IF NOT EXISTS idx_node_results_run ON graph_node_results(run_id);
CREATE INDEX IF NOT EXISTS idx_node_results_node ON graph_node_results(node_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_node_results_run_node ON graph_node_results(run_id, node_id);
"""
