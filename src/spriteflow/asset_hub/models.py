"""素材数据模型 + SQLite Schema DDL"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Asset(BaseModel):
    """统一素材模型"""

    id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))
    type: Literal["image", "video", "spritesheet"] = "image"
    source: Literal["uploaded", "generated", "derived"] = "uploaded"
    uri: str = ""                     # COS 对象路径
    hash: str = ""                    # 内容哈希（去重 + 缓存寻址）
    width: int | None = None
    height: int | None = None
    thumbnail: str | None = None      # 缩略图 URI
    tags: list[str] = Field(default_factory=list)
    parent_id: str | None = None      # 血缘：上游素材 id
    provenance: dict | None = None    # 生成它的工作流 id + 参数快照
    favorite: bool = False             # 是否收藏
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
"""
