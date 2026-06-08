"""Img2Img 节点 — 图生图（单参考图，适配 Seedream 字段）"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType
from ..providers.base import Capability


class Img2ImgNode(Node):
    """图生图节点（单参考图）"""

    INPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "generate"
    _node_type = "Img2Img"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("Img2Img 需要 router（能力路由器）")

        image = inputs.get("image")
        if image is None:
            raise ValueError("Img2Img 需要 image 输入")

        payload = {
            "prompt": params.get("prompt", ""),
            "image": image,
            "size": params.get("size", "2k"),
            "seed": params.get("seed"),
            "guidance_scale": params.get("guidance_scale"),
            "watermark": params.get("watermark", False),
            "output_format": params.get("output_format", "png"),
            "response_format": params.get("response_format", "url"),
        }

        result = await ctx.router.route(Capability.IMG2IMG, payload)

        output_image = result.get("image")
        if output_image is None:
            raise ValueError("img2img provider 未返回图片")

        ctx.log(f"图生图完成: prompt='{payload['prompt'][:50]}...'")
        ctx.set_node_inputs(self.node_id, {"prompt": payload["prompt"], "params": params})
        return {"image": output_image}
