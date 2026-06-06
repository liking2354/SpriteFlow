"""PackSpritesheet 节点 — 帧列表 → 拼合大图 + atlas JSON

输入: frames (IMAGE_BATCH)
输出: spritesheet (IMAGE)

支持三种 atlas 格式：godot / unity / phaser
可选：自动保存到 COS exports/ 并写入 AssetDB
"""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

from PIL import Image

from ..engine.node import Node
from ..engine.types import ParamSpec, PortType, Int, Str
from ..storage.base import StoragePrefix

# atlas JSON 格式列表
_ATLAS_FORMATS = ["godot", "unity", "phaser"]


def _build_godot_atlas(
    frame_count: int,
    cell_w: int,
    cell_h: int,
    columns: int,
    sheet_w: int,
    sheet_h: int,
) -> dict[str, Any]:
    """生成 Godot 格式的 atlas JSON"""
    frames = []
    for i in range(frame_count):
        col = i % columns
        row = i // columns
        frames.append({
            "filename": f"frame_{i}.png",
            "frame": {"x": col * cell_w, "y": row * cell_h, "w": cell_w, "h": cell_h},
        })
    return {
        "frames": frames,
        "meta": {"size": {"w": sheet_w, "h": sheet_h}, "format": "RGBA8888"},
    }


def _build_unity_atlas(
    frame_count: int,
    cell_w: int,
    cell_h: int,
    columns: int,
    sheet_w: int,
    sheet_h: int,
) -> dict[str, Any]:
    """生成 Unity 格式的 atlas JSON"""
    frames = {}
    for i in range(frame_count):
        col = i % columns
        row = i // columns
        frames[f"frame_{i}"] = {
            "frame": {"x": col * cell_w, "y": row * cell_h, "w": cell_w, "h": cell_h},
            "rotated": False,
            "trimmed": False,
            "spriteSourceSize": {"x": 0, "y": 0, "w": cell_w, "h": cell_h},
            "sourceSize": {"w": cell_w, "h": cell_h},
        }
    return {
        "frames": frames,
        "meta": {
            "app": "SpriteFlow",
            "version": "0.1.0",
            "size": {"w": sheet_w, "h": sheet_h},
            "format": "RGBA8888",
        },
    }


def _build_phaser_atlas(
    frame_count: int,
    cell_w: int,
    cell_h: int,
    columns: int,
    sheet_w: int,
    sheet_h: int,
) -> dict[str, Any]:
    """生成 Phaser 格式的 atlas JSON"""
    frames = {}
    for i in range(frame_count):
        col = i % columns
        row = i // columns
        frames[f"frame_{i}.png"] = {
            "frame": {"x": col * cell_w, "y": row * cell_h, "w": cell_w, "h": cell_h},
            "rotated": False,
            "trimmed": False,
            "spriteSourceSize": {"x": 0, "y": 0, "w": cell_w, "h": cell_h},
            "sourceSize": {"w": cell_w, "h": cell_h},
        }
    return {
        "frames": frames,
        "meta": {
            "app": "SpriteFlow",
            "version": "0.1.0",
            "size": {"w": sheet_w, "h": sheet_h},
        },
    }


_ATLAS_BUILDERS = {
    "godot": _build_godot_atlas,
    "unity": _build_unity_atlas,
    "phaser": _build_phaser_atlas,
}


class PackSpritesheetNode(Node):
    """精灵表打包节点

    帧列表 → 拼合大图 + atlas JSON → 导出
    """

    INPUTS: dict[str, PortType] = {"frames": PortType.IMAGE_BATCH}
    OUTPUTS: dict[str, PortType] = {"spritesheet": PortType.IMAGE}
    CATEGORY = "export"
    _node_type = "PackSpritesheet"

    PARAMS: list[ParamSpec] = [
        Int("columns", default=0, min_val=0, max_val=64),
        Int("cell_width", default=64, min_val=8, max_val=2048),
        Int("cell_height", default=64, min_val=8, max_val=2048),
        Int("padding", default=0, min_val=0, max_val=64),
        Str("format", default="godot", choices=_ATLAS_FORMATS),
    ]

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        frames: list = inputs.get("frames", [])
        if not frames:
            raise ValueError("PackSpritesheet 需要 frames 输入（IMAGE_BATCH）")

        columns: int = params.get("columns", 0)
        cell_w: int = params.get("cell_width", 64)
        cell_h: int = params.get("cell_height", 64)
        pad: int = params.get("padding", 0)
        fmt: str = params.get("format", "godot")
        save_asset: bool = params.get("save_asset", True)
        name: str = params.get("name", "spritesheet")

        if fmt not in _ATLAS_FORMATS:
            raise ValueError(f"不支持的 atlas 格式: {fmt}，可选: {_ATLAS_FORMATS}")

        frame_count = len(frames)

        # 1) 计算网格布局
        if columns <= 0:
            columns = int(frame_count ** 0.5) or 1
            # 确保列数不小于 ceil(n/rows) 的最小值
            while columns > 1 and (columns - 1) * ((frame_count + columns - 2) // (columns - 1)) >= frame_count:
                columns -= 1
            if columns < 1:
                columns = 1

        rows = (frame_count + columns - 1) // columns
        sheet_w = columns * cell_w + (columns + 1) * pad
        sheet_h = rows * cell_h + (rows + 1) * pad

        ctx.log(f"精灵表布局: {columns}×{rows} = {sheet_w}×{sheet_h}px")

        # 2) 创建画布并逐格粘贴
        sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

        for idx, frame in enumerate(frames):
            if not isinstance(frame, Image.Image):
                raise ValueError(f"第 {idx} 帧不是 PIL.Image，类型: {type(frame)}")

            col = idx % columns
            row = idx // columns
            x = pad + col * (cell_w + pad)
            y = pad + row * (cell_h + pad)

            # 缩放帧到目标单元格大小
            if frame.size != (cell_w, cell_h):
                frame = frame.resize((cell_w, cell_h), Image.LANCZOS)

            sheet.paste(frame, (x, y), frame)

        # 3) 生成 atlas JSON
        atlas = _ATLAS_BUILDERS[fmt](frame_count, cell_w, cell_h, columns, sheet_w, sheet_h)

        # 4) 可选：保存到 COS + AssetDB
        asset_id = ""
        if save_asset and hasattr(ctx, 'storage') and ctx.storage is not None:
            buf = io.BytesIO()
            sheet.save(buf, format="PNG")
            data = buf.getvalue()
            content_hash = hashlib.sha256(data).hexdigest()[:32]

            # 上传到 COS exports/
            file_key = f"{name}_{content_hash}.png"
            uri = await ctx.storage.upload(file_key, data, prefix=StoragePrefix.EXPORTS)

            # 生成缩略图
            thumb = sheet.copy()
            thumb.thumbnail((256, 256), Image.LANCZOS)
            thumb_buf = io.BytesIO()
            thumb.save(thumb_buf, format="PNG")
            thumb_data = thumb_buf.getvalue()
            thumb_key = f"{name}_{content_hash}.png"
            thumbnail_uri = await ctx.storage.upload(
                thumb_key, thumb_data, prefix=StoragePrefix.THUMBNAILS
            )

            # 写入 AssetDB
            if hasattr(ctx, 'db') and ctx.db is not None:
                from ..asset_hub.models import Asset
                asset = Asset(
                    type="spritesheet",
                    source="generated",
                    uri=uri,
                    hash=content_hash,
                    width=sheet_w,
                    height=sheet_h,
                    thumbnail=thumbnail_uri,
                    tags=params.get("tags", []),
                    provenance={
                        **atlas,
                        "frame_count": frame_count,
                        "cell_size": [cell_w, cell_h],
                        "atlas_format": fmt,
                    },
                )
                await ctx.db.create_asset(asset)
                asset_id = asset.id
                ctx.log(f"精灵表已保存: asset_id={asset_id}")

            ctx.log(f"精灵表已上传: {uri}")

        ctx.log(f"精灵表打包完成: {frame_count} 帧 → {sheet_w}×{sheet_h}px ({fmt} 格式)")
        return {
            "spritesheet": sheet,
            "atlas_json": json.dumps(atlas, ensure_ascii=False),
            "asset_id": asset_id,
            "columns": columns,
            "rows": rows,
        }
