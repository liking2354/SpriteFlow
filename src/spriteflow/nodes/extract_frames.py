"""ExtractFrames 节点 — 视频 → ffmpeg 抽帧 → 逐帧 rembg → SpriteAligner

输入: video_asset_id（参数）
输出: frames (IMAGE_BATCH)

流程：
  1. 通过 ctx.db 查找视频 asset URI
  2. ctx.storage.download() 下载视频到临时文件
  3. subprocess ffmpeg 按 fps 抽帧到临时目录
  4. PIL 加载每帧
  5. 可选：逐帧 rembg 去背景
  6. 可选：逐帧 SpriteAligner 对齐
  7. 清理临时文件，返回帧列表
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from typing import Any

from PIL import Image

from ..engine.node import Node
from ..engine.types import ParamSpec, PortType, Int, Str
from ..providers.base import Capability
from ..engine.sprite_aligner import SpriteAligner

# ffmpeg 常见路径列表
_FFMPEG_PATHS = [
    "ffmpeg",
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/homebrew/bin/ffmpeg",
]


def _find_ffmpeg() -> str:
    """在常见路径中查找 ffmpeg 二进制文件"""
    for path in _FFMPEG_PATHS:
        if shutil.which(path):
            return path
    raise RuntimeError(
        "未找到 ffmpeg。请安装: brew install ffmpeg (macOS) 或 apt install ffmpeg (Linux)"
    )


class ExtractFramesNode(Node):
    """视频抽帧节点

    视频 → ffmpeg 抽帧 → 可选 rembg → 可选 SpriteAligner → 帧列表
    """

    INPUTS: dict[str, PortType] = {}
    OUTPUTS: dict[str, PortType] = {"frames": PortType.IMAGE_BATCH}
    CATEGORY = "process"
    _node_type = "ExtractFrames"

    PARAMS: list[ParamSpec] = [
        Str("video_asset_id", required=True),
        Int("fps", default=8, min_val=1, max_val=60),
        Int("max_frames", default=16, min_val=1, max_val=256),
        Int("canvas_width", default=64, min_val=16, max_val=1024),
        Int("canvas_height", default=64, min_val=16, max_val=1024),
        Int("align_target_width", default=28, min_val=8, max_val=1024),
        Int("align_target_height", default=48, min_val=8, max_val=1024),
        Int("align_threshold", default=32, min_val=0, max_val=255),
        Int("padding", default=8, min_val=0, max_val=64),
    ]

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        video_asset_id: str = params["video_asset_id"]
        fps: int = params.get("fps", 8)
        max_frames: int = params.get("max_frames", 16)
        remove_bg: bool = params.get("remove_bg", True)
        do_align: bool = params.get("align", True)
        canvas_w: int = params.get("canvas_width", 64)
        canvas_h: int = params.get("canvas_height", 64)
        target_w: int = params.get("align_target_width", 28)
        target_h: int = params.get("align_target_height", 48)
        threshold: int = params.get("align_threshold", 32)
        padding: int = params.get("padding", 8)

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

        # 3) 检测 ffmpeg
        ffmpeg = _find_ffmpeg()
        ctx.log(f"使用 ffmpeg: {ffmpeg}")

        # 4) 创建临时目录用于抽帧
        tmp_dir = tempfile.mkdtemp(prefix="spriteflow_frames_")
        video_path = os.path.join(tmp_dir, "input_video.mp4")
        try:
            # 写入临时视频文件
            with open(video_path, "wb") as f:
                f.write(video_data)

            # 5) ffmpeg 抽帧
            # 先获取视频的帧率信息用于 -r 参数
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
            ctx.log(f"ffmpeg 抽帧: {' '.join(cmd)}")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode(errors="ignore")[:500]
                raise RuntimeError(f"ffmpeg 抽帧失败 (code={proc.returncode}): {error_msg}")

            # 6) 加载临时 PNG 为 PIL.Image 列表
            frames: list[Image.Image] = []
            frame_files = sorted(
                [f for f in os.listdir(tmp_dir) if f.startswith("frame_") and f.endswith(".png")]
            )
            ctx.log(f"ffmpeg 生成 {len(frame_files)} 个帧文件")

            for fname in frame_files[:max_frames]:
                fpath = os.path.join(tmp_dir, fname)
                img = Image.open(fpath).convert("RGBA")
                frames.append(img)

            if not frames:
                raise RuntimeError("ffmpeg 未生成任何帧")

            # 7) 逐帧处理：rembg + align
            processed: list[Image.Image] = []
            for idx, frame in enumerate(frames):
                ctx.log(f"处理第 {idx + 1}/{len(frames)} 帧...")

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

                processed.append(frame)

            ctx.log(f"抽帧完成: {len(processed)} 帧")
            return {"frames": processed}

        finally:
            # 清理临时文件
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
