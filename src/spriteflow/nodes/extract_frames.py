"""ExtractFrames 节点 — 视频 → ffmpeg 抽帧 → 逐帧 rembg → SpriteAligner → SpriteSheet

输入: video_asset_id（参数）
输出: frames (IMAGE_BATCH), sprite_sheet (IMAGE), index_json (JSON 元数据)

流程：
  1. 通过 ctx.db 查找视频 asset URI
  2. ctx.storage.download() 下载视频到临时文件
  3. ffprobe 探测视频元数据（时长、分辨率、帧率）
  4. subprocess ffmpeg 按时间戳精确抽帧到临时目录
  5. PIL 加载每帧
  6. 可选：逐帧 rembg 去背景
  7. 可选：逐帧 SpriteAligner 对齐
  8. 可选：合成序列帧 Sprite Sheet + 索引 JSON
  9. 清理临时文件，返回帧列表 + 精灵表
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import tempfile
from typing import Any

from PIL import Image

from ..engine.node import Node
from ..engine.types import ParamSpec, PortType, Int, Float, Str
from ..providers.base import Capability
from ..engine.sprite_aligner import SpriteAligner

# ffmpeg 常见路径列表
_FFMPEG_PATHS = [
    "ffmpeg",
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
]

# ffprobe 常见路径列表
_FFPROBE_PATHS = [
    "ffprobe",
    "/usr/bin/ffprobe",
    "/usr/local/bin/ffprobe",
    "/opt/homebrew/bin/ffprobe",
]


def _find_ffmpeg() -> str:
    """在常见路径中查找 ffmpeg 二进制文件"""
    for path in _FFMPEG_PATHS:
        if shutil.which(path):
            return path
    raise RuntimeError(
        "未找到 ffmpeg。请安装: brew install ffmpeg (macOS) 或 apt install ffmpeg (Linux)"
    )


def _find_ffprobe() -> str:
    """在常见路径中查找 ffprobe 二进制文件"""
    for path in _FFPROBE_PATHS:
        if shutil.which(path):
            return path
    raise RuntimeError(
        "未找到 ffprobe。请安装: brew install ffmpeg (macOS) 或 apt install ffmpeg (Linux)"
    )


def get_video_info(video_path: str) -> dict:
    """使用 ffprobe 获取视频元数据

    Returns:
        dict with keys: duration, width, height, fps, frame_count
    """
    ffprobe = _find_ffprobe()
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path,
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


def compute_layout(
    frame_count: int,
    frame_w: int,
    frame_h: int,
    spacing: int,
    layout_mode: str,
    columns: int | None = None,
) -> tuple[int, int, int, int]:
    """计算 Sprite Sheet 布局，返回 (cols, rows, sheet_w, sheet_h)

    Args:
        frame_count: 帧总数
        frame_w: 单帧宽度
        frame_h: 单帧高度
        spacing: 帧间距
        layout_mode: "fixed_columns" 或 "auto_square"
        columns: 固定列数（layout_mode="fixed_columns" 时使用）
    """
    if layout_mode == "fixed_columns" and columns and columns > 0:
        cols = columns
    else:
        cols = max(1, math.ceil(math.sqrt(frame_count)))

    rows = math.ceil(frame_count / cols) if frame_count else 0
    sheet_w = cols * (frame_w + spacing) - spacing
    sheet_h = rows * (frame_h + spacing) - spacing
    return cols, rows, sheet_w, sheet_h


def compose_sprite_sheet(
    frame_paths: list[str],
    timestamps: list[float],
    frame_w: int,
    frame_h: int,
    spacing: int,
    layout_mode: str,
    columns: int,
    output_path: str,
) -> dict:
    """合成序列帧 Sprite Sheet 并生成索引 JSON

    Args:
        frame_paths: 已处理的帧文件路径列表
        timestamps: 每帧对应的时间戳
        frame_w: 单帧宽度
        frame_h: 单帧高度
        spacing: 帧间距
        layout_mode: 布局模式
        columns: 固定列数
        output_path: 输出 PNG 路径

    Returns:
        索引数据 dict（version, frame_size, sheet_size, frames）
    """
    n = len(frame_paths)
    cols, rows, sheet_w, sheet_h = compute_layout(n, frame_w, frame_h, spacing, layout_mode, columns)

    sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    frames_index: list[dict] = []

    for i, (fp, t) in enumerate(zip(frame_paths, timestamps)):
        img = Image.open(fp).convert("RGBA")
        col = i % cols
        row = i // cols
        x = col * (frame_w + spacing)
        y = row * (frame_h + spacing)
        sheet.paste(img, (x, y), img)
        frames_index.append({
            "i": i,
            "x": x,
            "y": y,
            "w": frame_w,
            "h": frame_h,
            "t": round(t, 3),
        })

    sheet.save(output_path, "PNG")

    return {
        "version": "1.0",
        "frame_size": {"w": frame_w, "h": frame_h},
        "sheet_size": {"w": sheet_w, "h": sheet_h},
        "frames": frames_index,
    }


class ExtractFramesNode(Node):
    """视频抽帧节点

    视频 → ffprobe 探测 → ffmpeg 时间戳抽帧 → 可选 rembg → 可选 SpriteAligner → 帧列表 + 可选 SpriteSheet
    """

    INPUTS: dict[str, PortType] = {}
    OUTPUTS: dict[str, PortType] = {
        "frames": PortType.IMAGE_BATCH,
        "sprite_sheet": PortType.IMAGE,
    }
    CATEGORY = "process"
    _node_type = "ExtractFrames"

    PARAMS: list[ParamSpec] = [
        Str("video_asset_id", required=True),
        Int("fps", default=8, min_val=1, max_val=60),
        Int("max_frames", default=16, min_val=1, max_val=256),
        Float("start_sec", default=0.0, min_val=0.0),
        Float("end_sec", default=0.0, min_val=0.0),
        Int("canvas_width", default=64, min_val=16, max_val=1024),
        Int("canvas_height", default=64, min_val=16, max_val=1024),
        Int("align_target_width", default=28, min_val=8, max_val=1024),
        Int("align_target_height", default=48, min_val=8, max_val=1024),
        Int("align_threshold", default=32, min_val=0, max_val=255),
        Int("padding", default=8, min_val=0, max_val=64),
        Int("spacing", default=4, min_val=0, max_val=64),
        Str("layout_mode", default="auto_square", choices=["auto_square", "fixed_columns"]),
        Int("columns", default=8, min_val=1, max_val=64),
    ]

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        video_asset_id: str = params["video_asset_id"]
        fps: int = params.get("fps", 8)
        max_frames: int = params.get("max_frames", 16)
        start_sec: float = params.get("start_sec", 0.0)
        end_sec: float = params.get("end_sec", 0.0)
        remove_bg: bool = params.get("remove_bg", True)
        do_align: bool = params.get("align", True)
        do_sprite_sheet: bool = params.get("compose_sprite_sheet", True)
        canvas_w: int = params.get("canvas_width", 64)
        canvas_h: int = params.get("canvas_height", 64)
        target_w: int = params.get("align_target_width", 28)
        target_h: int = params.get("align_target_height", 48)
        threshold: int = params.get("align_threshold", 32)
        padding: int = params.get("padding", 8)
        spacing: int = params.get("spacing", 4)
        layout_mode: str = params.get("layout_mode", "auto_square")
        columns: int = params.get("columns", 8)

        if not video_asset_id:
            raise ValueError("ExtractFrames 需要 video_asset_id 参数")

        # 1) 查找视频 asset URI
        video_uri: str | None = None
        if hasattr(ctx, 'db') and ctx.db is not None:
            asset = await ctx.db.get_asset(video_asset_id)
            if asset and asset.type == "video":
                video_uri = asset.uri
            elif asset:
                raise ValueError(f"Asset {video_asset_id} 类型为 '{asset.type}'，需要 video 类型")
            else:
                raise ValueError(f"未找到视频 asset: {video_asset_id}")
        else:
            # ctx.db 不可用时，将 video_asset_id 作为 URI 直接使用
            video_uri = video_asset_id
        if not video_uri:
            raise ValueError(f"无法获取视频 URI: {video_asset_id}")

        if ctx.storage is None:
            raise ValueError("ExtractFrames 需要 storage 后端")

        # 2) 下载视频到临时文件
        ctx.log(f"下载视频: {video_uri}")
        video_data = await ctx.storage.download(video_uri)

        # 3) 检测 ffmpeg / ffprobe
        ffmpeg = _find_ffmpeg()
        ctx.log(f"使用 ffmpeg: {ffmpeg}")

        # 4) 创建临时目录用于抽帧
        tmp_dir = tempfile.mkdtemp(prefix="spriteflow_frames_")
        video_path = os.path.join(tmp_dir, "input_video.mp4")
        try:
            # 写入临时视频文件
            with open(video_path, "wb") as f:
                f.write(video_data)

            # 5) ffprobe 探测视频元数据
            video_info: dict | None = None
            try:
                video_info = get_video_info(video_path)
                ctx.log(
                    f"视频信息: {video_info['width']}x{video_info['height']}, "
                    f"{video_info['fps']:.1f} fps, {video_info['duration']:.1f}s"
                )
            except Exception as e:
                ctx.log(f"ffprobe 探测失败: {e}")

            # 6) 判断使用时间戳模式还是 fps 滤镜模式
            #    时间戳模式 → ffprobe 成功且视频时长已知，逐时间戳精确抽帧
            #    fps 滤镜模式 → 回退方案，批量抽帧兼容无 ffprobe 环境
            duration = video_info["duration"] if video_info else 0.0
            use_timestamp = video_info is not None and duration > 0

            if use_timestamp:
                # --- 时间戳精确抽帧模式 ---
                effective_end = end_sec if end_sec > 0 else duration
                effective_start = max(0.0, min(start_sec, duration))
                effective_end = max(effective_start, min(effective_end, duration))

                if effective_end <= effective_start:
                    effective_end = duration

                interval = 1.0 / fps
                timestamps: list[float] = []
                t = effective_start
                while t < effective_end and len(timestamps) < max_frames:
                    timestamps.append(t)
                    t += interval

                if not timestamps:
                    raise RuntimeError("抽帧时间范围为空，请调整 fps/start_sec/end_sec 参数")

                ctx.log(
                    f"抽帧模式=时间戳, {len(timestamps)} 帧 "
                    f"({effective_start:.1f}s → {effective_end:.1f}s, 间隔 {interval:.2f}s)"
                )

                saved_paths: list[str] = []
                for i, ts in enumerate(timestamps):
                    out_path = os.path.join(tmp_dir, f"frame_{i:04d}.png")
                    cmd = [
                        ffmpeg,
                        "-y",
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
                        ctx.log(f"  第 {i + 1} 帧抽帧失败 (t={ts:.2f}s): {error_msg}")
                        continue
                    saved_paths.append(out_path)

                if not saved_paths:
                    raise RuntimeError("ffmpeg 未生成任何帧")

                ctx.log(f"ffmpeg 成功抽取 {len(saved_paths)} 帧")
                timestamps = timestamps[:len(saved_paths)]
            else:
                # --- fps 滤镜批处理模式（回退，兼容无 ffprobe / 旧调用）---
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
                ctx.log(f"抽帧模式=fps滤镜, {fps}fps, 上限{max_frames}帧: {' '.join(cmd)}")

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
                    [f for f in os.listdir(tmp_dir) if f.startswith("frame_") and f.endswith(".png")]
                )
                ctx.log(f"ffmpeg 生成 {len(frame_files)} 个帧文件")

                saved_paths = [os.path.join(tmp_dir, fname) for fname in frame_files[:max_frames]]
                timestamps = [float(i) / fps for i in range(len(saved_paths))]

            # 8) 加载帧 + 处理
            processed: list[Image.Image] = []
            for idx, fpath in enumerate(saved_paths):
                ctx.log(f"处理第 {idx + 1}/{len(saved_paths)} 帧...")
                frame = Image.open(fpath).convert("RGBA")

                if remove_bg and ctx.router is not None:
                    try:
                        result = await ctx.router.route(Capability.REMOVE_BG, {"image": frame})
                        frame = result.get("image", frame)
                    except Exception as e:
                        ctx.log(f"  第 {idx + 1} 帧去背景失败，保留原图: {e}")

                if do_align:
                    frame = SpriteAligner.align(
                        frame,
                        canvas_width=canvas_w,
                        canvas_height=canvas_h,
                        target_width=target_w,
                        target_height=target_h,
                        detect_threshold=threshold,
                        padding=padding,
                    )
                    # 将处理后的帧写回临时文件（供 sprite sheet 合成使用）
                    frame.save(fpath, "PNG")

                processed.append(frame)

            ctx.log(f"抽帧完成: {len(processed)} 帧")

            # 9) 可选：合成 Sprite Sheet
            result: dict[str, Any] = {"frames": processed}
            if do_sprite_sheet and len(processed) > 1:
                # 使用对齐后的帧尺寸（若未对齐则用画布参数或第一帧尺寸）
                sframe_w = canvas_w if do_align else (processed[0].width if processed else 64)
                sframe_h = canvas_h if do_align else (processed[0].height if processed else 64)
                sheet_path = os.path.join(tmp_dir, "sprite_sheet.png")

                index_data = compose_sprite_sheet(
                    frame_paths=saved_paths[:len(processed)],
                    timestamps=timestamps,
                    frame_w=sframe_w,
                    frame_h=sframe_h,
                    spacing=spacing,
                    layout_mode=layout_mode,
                    columns=columns,
                    output_path=sheet_path,
                )

                # 加载合成图
                sheet_img = Image.open(sheet_path).convert("RGBA")
                result["sprite_sheet"] = sheet_img
                result["index_json"] = index_data
                ctx.log(
                    f"Sprite Sheet 合成: {index_data['sheet_size']['w']}x{index_data['sheet_size']['h']}, "
                    f"{len(index_data['frames'])} 帧"
                )

            return result

        finally:
            # 清理临时文件
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
