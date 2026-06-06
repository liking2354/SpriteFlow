"""SpriteAlign 节点 — 精灵图像对齐/裁剪/缩放/居中

解决 AI 生成图像尺寸不一致问题：
  输入：任意尺寸 RGBA 图像
  输出：统一画布尺寸的居中精灵帧
"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType, Int, Str
from ..engine.sprite_aligner import SpriteAligner


class SpriteAlignNode(Node):
    """精灵对齐节点

    输入：单张 RGBA 图像
    输出：对齐并适配画布后的单张图像
    全部为本地 PIL/NumPy 处理，无需远程 API。
    """

    INPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    PARAMS = [
        Int("canvas_width", default=64, min_val=16, max_val=4096),
        Int("canvas_height", default=64, min_val=16, max_val=4096),
        Int("target_width", default=28, min_val=4, max_val=4096),
        Int("target_height", default=48, min_val=4, max_val=4096),
        Int("detect_threshold", default=32, min_val=0, max_val=255),
        Int("padding", default=8, min_val=0, max_val=128),
        Str("auto_center", default="true", choices=["true", "false"]),
        Str("auto_crop", default="true", choices=["true", "false"]),
        Str("bottom_align", default="true", choices=["true", "false"]),
    ]
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "process"
    _node_type = "SpriteAlign"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        image = inputs.get("image")
        if image is None:
            raise ValueError("SpriteAlign 需要 image 输入")

        to_bool = lambda v: v if isinstance(v, bool) else str(v).lower() == "true"

        aligned = SpriteAligner.align(
            image=image,
            canvas_width=int(params.get("canvas_width", 64)),
            canvas_height=int(params.get("canvas_height", 64)),
            target_width=int(params.get("target_width", 28)),
            target_height=int(params.get("target_height", 48)),
            detect_threshold=int(params.get("detect_threshold", 32)),
            padding=int(params.get("padding", 8)),
            auto_center=to_bool(params.get("auto_center", True)),
            auto_crop=to_bool(params.get("auto_crop", True)),
            bottom_align=to_bool(params.get("bottom_align", True)),
        )

        ctx.log(f"SpriteAlign: {aligned.size[0]}x{aligned.size[1]}")
        return {"image": aligned}
