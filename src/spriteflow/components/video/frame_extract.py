"""
VideoFrameExtract 组件 — 视频序列帧抽取

从视频中按指定帧率抽取序列帧，可选去背景和裁剪，
输出为 image_batch 供下游节点使用。

流程：
  1. 下载视频（支持本地 workflow runs URL / 远程 URL / COS URL）
  2. ffprobe 探测视频元数据
  3. ffmpeg 按时间戳精确抽帧（回退 fps 滤镜模式）
  4. 可选：逐帧 rembg 去背景
  5. 可选：逐帧裁剪
  6. 逐帧上传到存储，返回 image_batch
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any

import httpx
import numpy as np
from PIL import Image

from ..base import Component, ComponentMeta
from ..utils import save_image_local

logger = logging.getLogger(__name__)

# ffmpeg / ffprobe 路径查找
_FFMPEG_PATHS = ["ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/homebrew/bin/ffmpeg"]
_FFPROBE_PATHS = ["ffprobe", "/usr/bin/ffprobe", "/usr/local/bin/ffprobe", "/opt/homebrew/bin/ffprobe"]


def _find_ffmpeg() -> str:
    for path in _FFMPEG_PATHS:
        if shutil.which(path):
            return path
    raise RuntimeError("未找到 ffmpeg。请安装: brew install ffmpeg (macOS) 或 apt install ffmpeg (Linux)")


def _find_ffprobe() -> str:
    for path in _FFPROBE_PATHS:
        if shutil.which(path):
            return path
    raise RuntimeError("未找到 ffprobe。请安装: brew install ffmpeg (macOS) 或 apt install ffmpeg (Linux)")


def _get_video_info(video_path: str) -> dict:
    """使用 ffprobe 获取视频元数据"""
    ffprobe = _find_ffprobe()
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 探测失败: {result.stderr[:300]}")
    data = json.loads(result.stdout)

    duration = 0.0
    width, height = 0, 0
    fps = 30.0

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            if "r_frame_rate" in stream:
                parts = stream["r_frame_rate"].split("/")
                num, den = int(parts[0]), int(parts[1]) if len(parts) > 1 else 1
                fps = num / den if den else 30.0
            break

    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (ValueError, KeyError, TypeError):
        duration = 0.0

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": int(duration * fps) if duration and fps else 0,
    }


def _remove_background(image: Image.Image, session_name: str | None = None) -> Image.Image:
    """使用 rembg 去除背景（同步，在线程池中调用）"""
    try:
        from rembg import remove
    except ImportError:
        raise ImportError("rembg 未安装，请执行: pip install rembg")

    if session_name:
        from rembg.session_factory import new_session
        session = new_session(session_name)
    else:
        session = None

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    output = remove(image, session=session)
    return output.convert("RGBA")


async def _download_video(url: str, dest_path: str) -> str:
    """下载视频到指定路径（本地 workflow runs URL 直接读取，避免 HTTP 回环）"""
    # 检测本地 workflow runs URL
    local_match = re.search(r"/api/workflow/runs/([^/]+)/outputs/(.+)", url)
    if local_match:
        from spriteflow.config import settings
        run_id, filename = local_match.group(1), local_match.group(2)
        filepath = settings.workflow_runs_dir / run_id / "outputs" / filename
        if filepath.is_file():
            shutil.copy2(str(filepath), dest_path)
            return dest_path

    # 远程 URL 下载
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(resp.content)
    return dest_path


async def _upload_image(image: Image.Image, filename_prefix: str = "frame") -> str:
    """上传图片到存储，返回可访问的 URL"""
    from spriteflow.api.deps import get_storage
    from spriteflow.storage.base import StoragePrefix

    storage = get_storage()

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data = buf.getvalue()

    content_hash = hashlib.sha256(data).hexdigest()[:32]
    file_key = f"{filename_prefix}_{content_hash}.png"

    uri = await storage.upload(file_key, data, prefix=StoragePrefix.AI_PROCESSED, content_type="image/png")

    try:
        url = await storage.get_presigned_url(uri)
    except Exception:
        url = uri

    return url


# ===== Key Frame Selection (ported from /video-frames ExtractTab.tsx) =====
_THUMB = 32
_THUMB_PX = _THUMB * _THUMB  # 1024


def _compute_frame_vectors(images: list[Image.Image]) -> tuple[list[np.ndarray], list[int]]:
    """Resize each image to 32x32 grayscale, flatten, mean-subtract."""
    vectors: list[np.ndarray] = []
    valid_indices: list[int] = []
    for i, img in enumerate(images):
        try:
            thumb = img.convert("RGB").resize((_THUMB, _THUMB), Image.LANCZOS)
            arr = np.array(thumb, dtype=np.float64)
            gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
            v = gray.flatten()
            v -= v.mean()
            vectors.append(v)
            valid_indices.append(i)
        except Exception as e:
            logger.warning("[VideoFrameExtract] vector for frame %d failed: %s", i, e)
    return vectors, valid_indices


def _vector_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(np.abs(a - b)) / (_THUMB_PX * 255))


def _uniform_select(valid_indices: list[int], target: int) -> list[int]:
    n = len(valid_indices)
    if n <= target:
        return list(valid_indices)
    if target <= 1:
        return [valid_indices[0]]
    return [valid_indices[round(i * (n - 1) / (target - 1))] for i in range(target)]


def _diversity_select(vectors: list[np.ndarray], valid_indices: list[int], target: int) -> list[int]:
    m = len(vectors)
    if m <= target:
        return list(valid_indices)
    selected = [0]
    selected_set = {0}
    min_dist = np.full(m, np.inf)
    for i in range(1, m):
        min_dist[i] = _vector_diff(vectors[0], vectors[i])
    while len(selected) < target:
        best, best_dist = -1, -1.0
        for i in range(m):
            if i not in selected_set and min_dist[i] > best_dist:
                best_dist = min_dist[i]
                best = i
        if best < 0:
            break
        selected.append(best)
        selected_set.add(best)
        for i in range(m):
            if i not in selected_set:
                d2 = _vector_diff(vectors[best], vectors[i])
                if d2 < min_dist[i]:
                    min_dist[i] = d2
    return sorted(valid_indices[s] for s in selected)


def _detect_cycle_period(diffs: list[float]) -> int | None:
    n = len(diffs)
    if n < 6:
        return None
    mean = sum(diffs) / n
    norm = [d - mean for d in diffs]
    max_lag = n // 2
    auto_corr: list[float] = []
    for lag in range(2, max_lag + 1):
        s = sum(norm[i] * norm[i + lag] for i in range(n - lag))
        auto_corr.append(s / (n - lag))
    if not auto_corr:
        return None
    max_corr = max(auto_corr)
    if max_corr <= 0:
        return None
    for i in range(1, len(auto_corr) - 1):
        if (auto_corr[i] > 0
                and auto_corr[i] > auto_corr[i - 1] * 0.9
                and auto_corr[i] >= auto_corr[i + 1]
                and auto_corr[i] > max_corr * 0.35):
            return i + 2
    return None


def _cycle_detect_and_sample(
    vectors: list[np.ndarray], valid_indices: list[int], target: int
) -> tuple[list[int], int | None]:
    n = len(valid_indices)
    if n <= target:
        return list(valid_indices), None
    m = len(vectors)
    if m <= target:
        return list(valid_indices), None
    diffs = [_vector_diff(vectors[i], vectors[i + 1]) for i in range(m - 1)]
    smoothed: list[float] = []
    for i in range(len(diffs)):
        s, cnt = diffs[i], 1
        if i > 0:
            s += diffs[i - 1]
            cnt += 1
        if i < len(diffs) - 1:
            s += diffs[i + 1]
            cnt += 1
        smoothed.append(s / cnt)
    cycle_len = _detect_cycle_period(smoothed)
    if cycle_len and cycle_len >= 4 and cycle_len <= n / 2:
        start_idx, min_val = 0, float("inf")
        for i in range(min(cycle_len, len(smoothed))):
            if smoothed[i] < min_val:
                min_val = smoothed[i]
                start_idx = i
        end_idx = min(start_idx + cycle_len, len(valid_indices))
        range_len = end_idx - start_idx
        if target <= 1:
            return [valid_indices[start_idx]], cycle_len
        indices = [
            valid_indices[min(start_idx + round(i * (range_len - 1) / (target - 1)), len(valid_indices) - 1)]
            for i in range(target)
        ]
    else:
        indices = _uniform_select(valid_indices, target)
    return indices, cycle_len


class VideoFrameExtractComponent(Component):
    """视频序列帧抽取组件"""

    @property
    def meta(self) -> ComponentMeta:
        return ComponentMeta(
            component_id="video-frame-extract",
            display_name="视频序列帧",
            category="video",
            subcategory="processing",
            description="从视频中按帧率抽取序列帧，可选 AI 去背景和裁剪。支持关键帧选择（循环检测/均匀/差异最大），输出可循环播放的序列帧。支持本地视频 URL、COS 远程 URL 或上游节点输入。",
            version="1.0.0",
            icon="🎬",
            output_type="image_batch",
            credential_schema={},
            input_schema={
                "video_url": {
                    "type": "string",
                    "title": "视频 URL",
                    "description": "待抽取序列帧的视频 URL（支持上游连线输入、素材库选择或手动填写）",
                    "format": "uri",
                },
                "fps": {
                    "type": "integer",
                    "title": "抽帧帧率",
                    "description": "每秒抽取多少帧（1~60，默认 8）",
                    "default": 8,
                    "minimum": 1,
                    "maximum": 60,
                },
                "max_frames": {
                    "type": "integer",
                    "title": "最大帧数",
                    "description": "最多抽取多少帧（1~300，默认 300）。先抽取全部帧，再通过关键帧选择筛选",
                    "default": 300,
                    "minimum": 1,
                    "maximum": 300,
                },
                "start_sec": {
                    "type": "number",
                    "title": "起始时间(秒)",
                    "description": "从视频的第几秒开始抽帧（0=从头开始）",
                    "default": 0,
                    "minimum": 0,
                },
                "end_sec": {
                    "type": "number",
                    "title": "结束时间(秒)",
                    "description": "抽帧截止时间（0=到视频结尾）",
                    "default": 0,
                    "minimum": 0,
                },
                "auto_remove_bg": {
                    "type": "boolean",
                    "title": "AI 去背景",
                    "description": "对每帧使用 rembg AI 去除背景（需要 onnxruntime）",
                    "default": False,
                },
                "remove_bg_model": {
                    "type": "string",
                    "title": "去背景模型",
                    "description": "选择 rembg 模型",
                    "enum": ["isnet-general-use", "u2net", "u2net_human_seg", "silueta", ""],
                    "enumNames": [
                        "通用首选 (isnet)",
                        "u2net",
                        "人像分割 (u2net_human_seg)",
                        "silueta",
                        "默认模型",
                    ],
                    "default": "isnet-general-use",
                },
                "crop_enabled": {
                    "type": "boolean",
                    "title": "启用裁剪",
                    "description": "对每帧进行像素裁剪（去除画面边缘不需要的区域）",
                    "default": False,
                },
                "crop_left": {
                    "type": "integer",
                    "title": "左裁剪(像素)",
                    "description": "从左侧裁剪掉的像素数",
                    "default": 0,
                    "minimum": 0,
                },
                "crop_right": {
                    "type": "integer",
                    "title": "右裁剪(像素)",
                    "description": "从右侧裁剪掉的像素数",
                    "default": 0,
                    "minimum": 0,
                },
                "crop_top": {
                    "type": "integer",
                    "title": "上裁剪(像素)",
                    "description": "从顶部裁剪掉的像素数",
                    "default": 0,
                    "minimum": 0,
                },
                "crop_bottom": {
                    "type": "integer",
                    "title": "下裁剪(像素)",
                    "description": "从底部裁剪掉的像素数",
                    "default": 0,
                    "minimum": 0,
                },
                "key_frame_mode": {
                    "type": "string",
                    "title": "关键帧选择",
                    "description": "抽帧后自动选择关键帧：none=输出全部帧，uniform=均匀采样，cycle=循环检测（选可循环播放的帧），diversity=差异最大",
                    "enum": ["none", "uniform", "cycle", "diversity"],
                    "enumNames": ["不选择（全部帧）", "均匀采样", "循环检测", "差异最大"],
                    "default": "none",
                },
                "key_frame_count": {
                    "type": "integer",
                    "title": "关键帧数量",
                    "description": "选择多少张关键帧（默认 8，仅当关键帧选择不为 none 时生效）",
                    "default": 8,
                    "minimum": 1,
                    "maximum": 64,
                },
            },
            input_required=["video_url"],
        )

    async def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        video_url = inputs.get("video_url", "")
        if not video_url:
            errors.append("请提供视频 URL（video_url 不能为空）")
        return errors

    async def execute(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        video_url = inputs.get("video_url", "")
        if not video_url:
            raise ValueError("缺少视频 URL")

        # 参数提取（inputs 和 params 合并，params 优先）
        def _get(key: str, default: Any = None) -> Any:
            val = params.get(key)
            if val is None:
                val = inputs.get(key)
            if val is None:
                return default
            return val

        def _get_int(key: str, default: int) -> int:
            val = _get(key, default)
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def _get_float(key: str, default: float) -> float:
            val = _get(key, default)
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        def _get_bool(key: str, default: bool) -> bool:
            val = _get(key, default)
            if isinstance(val, bool):
                return val
            if val is not None:
                return str(val).lower() == "true"
            return default

        fps = max(1, min(60, _get_int("fps", 8)))
        max_frames = max(1, min(300, _get_int("max_frames", 300)))
        start_sec = max(0.0, _get_float("start_sec", 0.0))
        end_sec = max(0.0, _get_float("end_sec", 0.0))
        auto_remove_bg = _get_bool("auto_remove_bg", False)
        remove_bg_model = _get("remove_bg_model", "isnet-general-use") or "isnet-general-use"
        if remove_bg_model == "":
            remove_bg_model = None
        crop_enabled = _get_bool("crop_enabled", False)
        crop_left = max(0, _get_int("crop_left", 0))
        crop_right = max(0, _get_int("crop_right", 0))
        crop_top = max(0, _get_int("crop_top", 0))
        crop_bottom = max(0, _get_int("crop_bottom", 0))
        key_frame_mode = str(_get("key_frame_mode", "none") or "none")
        key_frame_count = max(1, _get_int("key_frame_count", 8))

        logger.info(
            "[VideoFrameExtract] video=%s fps=%d max_frames=%d start=%.1f end=%.1f "
            "remove_bg=%s crop=%s",
            video_url[:120], fps, max_frames, start_sec, end_sec,
            auto_remove_bg, crop_enabled,
        )

        # 1. 下载视频到临时文件
        tmp_dir = tempfile.mkdtemp(prefix="spriteflow_vfe_")
        video_path = os.path.join(tmp_dir, "input_video.mp4")
        try:
            await _download_video(video_url, video_path)
            logger.info("[VideoFrameExtract] video downloaded: %s", video_path)

            # 2. ffprobe 探测视频元数据
            ffmpeg = _find_ffmpeg()
            video_info: dict | None = None
            try:
                video_info = _get_video_info(video_path)
                logger.info(
                    "[VideoFrameExtract] video info: %dx%d, %.1f fps, %.1fs",
                    video_info["width"], video_info["height"],
                    video_info["fps"], video_info["duration"],
                )
            except Exception as e:
                logger.warning("[VideoFrameExtract] ffprobe failed: %s", e)

            # 3. 抽帧
            duration = video_info["duration"] if video_info else 0.0
            use_timestamp = video_info is not None and duration > 0

            saved_paths: list[str] = []
            timestamps: list[float] = []

            if use_timestamp:
                # 时间戳精确抽帧模式
                effective_end = end_sec if end_sec > 0 else duration
                effective_start = max(0.0, min(start_sec, duration))
                effective_end = max(effective_start, min(effective_end, duration))
                if effective_end <= effective_start:
                    effective_end = duration

                interval = 1.0 / fps
                t = effective_start
                while t < effective_end and len(timestamps) < max_frames:
                    timestamps.append(t)
                    t += interval

                if not timestamps:
                    raise RuntimeError("抽帧时间范围为空，请调整 fps/start_sec/end_sec 参数")

                logger.info(
                    "[VideoFrameExtract] timestamp mode: %d frames (%.1fs → %.1fs, interval %.2fs)",
                    len(timestamps), effective_start, effective_end, interval,
                )

                for i, ts in enumerate(timestamps):
                    out_path = os.path.join(tmp_dir, f"frame_{i:04d}.png")
                    cmd = [
                        ffmpeg, "-y",
                        "-ss", str(ts),
                        "-i", video_path,
                        "-vframes", "1",
                        "-f", "image2",
                        "-q:v", "2",
                        out_path,
                    ]
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _stdout, _stderr = await proc.communicate()
                    if proc.returncode != 0:
                        error_msg = _stderr.decode(errors="ignore")[:300]
                        logger.warning("[VideoFrameExtract] frame %d failed (t=%.2fs): %s", i, ts, error_msg)
                        continue
                    saved_paths.append(out_path)

                if not saved_paths:
                    raise RuntimeError("ffmpeg 未生成任何帧")
                timestamps = timestamps[:len(saved_paths)]
                logger.info("[VideoFrameExtract] ffmpeg extracted %d frames", len(saved_paths))
            else:
                # fps 滤镜批处理模式（回退）
                output_pattern = os.path.join(tmp_dir, "frame_%04d.png")
                cmd = [
                    ffmpeg,
                    "-i", video_path,
                    "-vf", f"fps={fps}",
                    "-vframes", str(max_frames),
                    "-q:v", "2",
                    "-y",
                    output_pattern,
                ]
                logger.info("[VideoFrameExtract] fps filter mode: %dfps, max %d frames", fps, max_frames)

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout, _stderr = await proc.communicate()
                if proc.returncode != 0:
                    error_msg = _stderr.decode(errors="ignore")[:500]
                    raise RuntimeError(f"ffmpeg 抽帧失败 (code={proc.returncode}): {error_msg}")

                frame_files = sorted(
                    f for f in os.listdir(tmp_dir)
                    if f.startswith("frame_") and f.endswith(".png")
                )
                saved_paths = [os.path.join(tmp_dir, f) for f in frame_files[:max_frames]]
                timestamps = [float(i) / fps for i in range(len(saved_paths))]
                logger.info("[VideoFrameExtract] ffmpeg generated %d frames", len(saved_paths))

            # 4. 逐帧处理（去背景 + 裁剪）
            processed_frames: list[Image.Image] = []
            for idx, fpath in enumerate(saved_paths):
                frame = Image.open(fpath).convert("RGBA")

                # 裁剪
                if crop_enabled and (crop_left or crop_right or crop_top or crop_bottom):
                    w, h = frame.size
                    left = min(crop_left, w - 1)
                    top = min(crop_top, h - 1)
                    right = max(left + 1, w - crop_right)
                    bottom = max(top + 1, h - crop_bottom)
                    frame = frame.crop((left, top, right, bottom))

                # 去背景
                if auto_remove_bg:
                    try:
                        frame = await asyncio.to_thread(_remove_background, frame, remove_bg_model)
                    except Exception as e:
                        logger.warning("[VideoFrameExtract] frame %d rembg failed, keeping original: %s", idx, e)

                processed_frames.append(frame)

            logger.info("[VideoFrameExtract] processed %d frames", len(processed_frames))

            # 4.5 关键帧选择（循环检测 / 均匀 / 差异最大）
            cycle_len_report: int | None = None
            if key_frame_mode != "none" and len(processed_frames) > key_frame_count:
                logger.info(
                    "[VideoFrameExtract] key frame selection: mode=%s target=%d from %d frames",
                    key_frame_mode, key_frame_count, len(processed_frames),
                )
                vectors, valid_indices = _compute_frame_vectors(processed_frames)
                if key_frame_mode == "uniform":
                    selected = _uniform_select(valid_indices, key_frame_count)
                elif key_frame_mode == "diversity":
                    selected = _diversity_select(vectors, valid_indices, key_frame_count)
                elif key_frame_mode == "cycle":
                    selected, cycle_len_report = _cycle_detect_and_sample(
                        vectors, valid_indices, key_frame_count
                    )
                else:
                    selected = list(range(len(processed_frames)))

                processed_frames = [processed_frames[i] for i in selected]
                timestamps = [timestamps[i] for i in selected if i < len(timestamps)]
                logger.info(
                    "[VideoFrameExtract] key frame selection done: %d frames (cycle_len=%s)",
                    len(processed_frames), cycle_len_report,
                )
            elif key_frame_mode != "none":
                logger.info(
                    "[VideoFrameExtract] key frame selection skipped: %d frames <= target %d",
                    len(processed_frames), key_frame_count,
                )

            # 5. 逐帧保存到本地
            urls: list[str] = []
            for i, img in enumerate(processed_frames):
                url = await save_image_local(img, f"frame_{i}")
                urls.append(url)
                logger.info("[VideoFrameExtract] frame %d saved: %s", i, url[:120])

            # 6. 构建输出
            outputs = [
                {"type": "image_url", "value": url}
                for url in urls
            ]

            logger.info("[VideoFrameExtract] done: %d images", len(outputs))
            return {
                "outputs": outputs,
                "meta": {
                    "total": len(outputs),
                    "fps": fps,
                    "max_frames": max_frames,
                    "key_frame_mode": key_frame_mode,
                    "key_frame_count": key_frame_count,
                    "cycle_len": cycle_len_report,
                    "all_urls": ",".join(urls),
                    "video_info": video_info or {},
                    "timestamps": [round(t, 3) for t in timestamps],
                },
            }

        finally:
            # 清理临时文件
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
