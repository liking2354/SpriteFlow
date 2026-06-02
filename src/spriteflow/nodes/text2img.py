"""Text2Img 节点 — 文生图（适配 Seedream 字段）"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType
from ..providers.base import Capability


class Text2ImgNode(Node):
    """文生图节点

    声明需要 text2img 能力，由路由层决定实际调用的 provider（默认 seedream）。
    """

    INPUTS: dict[str, PortType] = {}
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "generate"
    _node_type = "Text2Img"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("Text2Img 需要 router（能力路由器）")

        payload = {
            "prompt": params.get("prompt", ""),
            "size": params.get("size", "2K"),
            "seed": params.get("seed"),
            "guidance_scale": params.get("guidance_scale"),
            "watermark": params.get("watermark", False),
            "output_format": params.get("output_format", "png"),
            "response_format": params.get("response_format", "url"),
            "web_search": params.get("web_search", False),
        }

        result = await ctx.router.route(Capability.TEXT2IMG, payload)

        image = result.get("image")
        if image is None:
            raise ValueError("text2img provider 未返回图片")

        ctx.log(f"文生图完成: prompt='{payload['prompt'][:50]}...'")
        return {"image": image}
