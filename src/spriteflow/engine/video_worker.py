"""视频任务后台 worker（独立 asyncio 任务）

职责：
  - 周期性扫描本地 video_tasks 表中未完成（queued/running）的任务
  - 对每条任务调用 Seedance fetch_task
  - 一旦 succeeded：立即下载视频字节 → IngestPipeline 落库 COS → 更新 result_asset_id
  - failed/expired/cancelled：写入 error_msg、终态

只在引擎进程里启动一个 worker（单实例服务足够）。
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional

from ..asset_hub.db import AssetDB
from ..asset_hub.ingest import IngestPipeline
from ..asset_hub.video_models import VideoTask
from ..providers.seedance import SeedanceProvider
from ..config import settings

log = logging.getLogger(__name__)


SETTLED = {"succeeded", "failed", "cancelled", "expired"}


class VideoWorker:
    def __init__(
        self,
        db: AssetDB,
        ingest: IngestPipeline,
        seedance: SeedanceProvider,
        api_key: str,
        poll_interval: float | None = None,
    ) -> None:
        self.db = db
        self.ingest = ingest
        self.seedance = seedance
        self.api_key = api_key
        self.poll_interval = poll_interval or settings.seedance_poll_interval_sec
        self._task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="video-worker")
        log.info("[VideoWorker] started, interval=%.1fs", self.poll_interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as e:  # noqa: BLE001
                log.error("[VideoWorker] tick error: %s\n%s", e, traceback.format_exc())
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except asyncio.TimeoutError:
                continue
            else:
                break

    async def _tick(self) -> None:
        if not self.api_key:
            return  # 未配置 ARK_API_KEY，worker 直接 idle
        unsettled = await self.db.list_unsettled_video_tasks()
        if not unsettled:
            return
        for t in unsettled:
            if not t.provider_task_id:
                # 还没拿到 provider_task_id，跳过（创建接口已直接写入，正常不会出现）
                continue
            await self._sync_one(t)

    async def _sync_one(self, t: VideoTask) -> None:
        try:
            payload = await self.seedance.fetch_task(t.provider_task_id, api_key=self.api_key)
        except Exception as e:  # noqa: BLE001
            log.warning("[VideoWorker] fetch %s failed: %s", t.provider_task_id, e)
            return

        status = payload.get("status") or t.status
        now = datetime.now().isoformat()
        update_kwargs: dict = {"status": status, "updated_at": now}

        # 失败信息
        err = payload.get("error")
        if isinstance(err, dict):
            code = err.get("code")
            msg = err.get("message", str(err))
            update_kwargs["error"] = f"{code}: {msg}" if code else str(msg)

        # usage
        usage = payload.get("usage") or {}
        if isinstance(usage, dict):
            tot = usage.get("completion_tokens") or usage.get("total_tokens")
            if isinstance(tot, int):
                update_kwargs["usage_tokens"] = tot

        if status == "succeeded":
            content = payload.get("content") or {}
            video_url = content.get("video_url")
            last_frame_url = content.get("last_frame_url")
            update_kwargs["completed_at"] = now

            if video_url and not t.result_asset_id:
                try:
                    asset = await self._download_and_save_video(video_url, t)
                    update_kwargs["result_asset_id"] = asset.id
                except Exception as e:  # noqa: BLE001
                    log.error("[VideoWorker] save video failed: %s", e)
                    update_kwargs["status"] = "failed"
                    update_kwargs["error"] = f"download_or_save_failed: {e}"

            if last_frame_url and not t.last_frame_asset_id:
                try:
                    last_asset = await self._download_and_save_last_frame(last_frame_url, t)
                    update_kwargs["last_frame_asset_id"] = last_asset.id
                except Exception as e:  # noqa: BLE001
                    log.warning("[VideoWorker] save last_frame failed: %s", e)

        if status in SETTLED and "completed_at" not in update_kwargs:
            update_kwargs["completed_at"] = now

        await self.db.update_video_task(t.id, **update_kwargs)

    async def _download_and_save_video(self, url: str, t: VideoTask):
        data = await self.seedance.download_video(url)
        return await self.ingest.ingest_video(
            data,
            ext="mp4",
            content_type="video/mp4",
            tags=["video", f"mode:{t.mode}"],
            provenance={
                "task_id": t.id,
                "provider_task_id": t.provider_task_id,
                "model": t.model,
                "mode": t.mode,
                "prompt": t.prompt,
                "params": t.params,
            },
        )

    async def _download_and_save_last_frame(self, url: str, t: VideoTask):
        data = await self.seedance.download_video(url)  # 同方法可拉任意 URL
        # 尾帧是图片（PNG/JPG），用通用 ingest 走规格化 + 缩略
        return await self.ingest.ingest(
            data,
            filename=f"{t.id}_last_frame.png",
            source="generated",
            tags=["video_last_frame", f"task:{t.id}"],
            provenance={
                "task_id": t.id,
                "provider_task_id": t.provider_task_id,
                "model": t.model,
                "mode": "video_last_frame",
            },
        )
