"""视频生成任务模型 + SQLite DDL"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


VideoStatus = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "expired"
]


class VideoTask(BaseModel):
    """视频生成任务记录"""

    id: str = Field(default_factory=lambda: f"vt_{uuid.uuid4().hex[:12]}")
    provider: str = "seedance"
    provider_task_id: str | None = None
    model: str = "doubao-seedance-2-0-260128"
    mode: str = "text2video"  # text2video | image2video_first | first_last | multi_ref
    prompt: str = ""
    params: dict[str, Any] = Field(default_factory=dict)   # ratio/duration/resolution/seed/...
    inputs: dict[str, Any] = Field(default_factory=dict)   # {first_frame_asset_id, last_frame_asset_id, ref_asset_ids}
    status: VideoStatus = "queued"
    error: str | None = None
    result_asset_id: str | None = None        # 下载入库后的 asset id
    last_frame_asset_id: str | None = None    # 尾帧（return_last_frame=true 时）
    usage_tokens: int | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None


VIDEO_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS video_tasks (
    id                  TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    provider_task_id    TEXT,
    model               TEXT NOT NULL,
    mode                TEXT NOT NULL,
    prompt              TEXT NOT NULL DEFAULT '',
    params              TEXT,                  -- JSON
    inputs              TEXT,                  -- JSON
    status              TEXT NOT NULL DEFAULT 'queued',
    error               TEXT,
    result_asset_id     TEXT,
    last_frame_asset_id TEXT,
    usage_tokens        INTEGER,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    completed_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_video_tasks_status   ON video_tasks(status);
CREATE INDEX IF NOT EXISTS idx_video_tasks_created  ON video_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_video_tasks_provider ON video_tasks(provider_task_id);
"""
