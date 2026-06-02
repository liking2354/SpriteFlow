"""MultiImageFusion 节点 — 多图融合（多参考图 → 单图）

典型场景：把图1的人物穿上图2的服装，置于图3的场景中。
"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType
from ..providers.base import Capability


class MultiImageFusionNode(Node):
    """多图融合节点

    输入：两张或更多参考图 + prompt
    输出：单张融合图

    支持两种输入方式：
      1. inputs.images: list[PIL.Image]            （由上游 batch/列表节点产出）
      2. params.image_urls: list[str]              （直接给 URL 列表，方便手写 yaml）
      3. inputs.image_a/image_b/image_c            （命名参考图，最多 4 张）
    """

    INPUTS: dict[str, PortType] = {
        "images": PortType.IMAGE_BATCH,
    }
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "generate"
    _node_type = "MultiImageFusion"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("MultiImageFusion 需要 router")

        # 收集参考图
        refs: list = []
        batch = inputs.get("images")
        if batch:
            if isinstance(batch, list):
                refs.extend(batch)
            else:
                refs.append(batch)

        for key in ("image_a", "image_b", "image_c", "image_d"):
            if (img := inputs.get(key)) is not None:
                refs.append(img)

        url_list = params.get("image_urls") or []
        refs.extend(url_list)

        if len(refs) < 2:
            raise ValueError(
                f"MultiImageFusion 需要至少 2 张参考图，当前只有 {len(refs)} 张"
            )

        payload = {
            "prompt": params.get("prompt", ""),
            "image": refs,
            "size": params.get("size", "2K"),
            "seed": params.get("seed"),
            "watermark": params.get("watermark", False),
            "output_format": params.get("output_format", "png"),
            "response_format": params.get("response_format", "url"),
        }

        result = await ctx.router.route(Capability.MULTI_IMAGE_FUSION, payload)
        image = result.get("image")
        if image is None:
            raise ValueError("multi_image_fusion provider 未返回图片")

        ctx.log(f"多图融合完成: refs={len(refs)} prompt='{payload['prompt'][:40]}...'")
        return {"image": image}
