"""RemoveBG 节点 — 去背景"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType
from ..providers.base import Capability


class RemoveBGNode(Node):
    """去背景节点

    声明需要 remove_bg 能力，由路由层决定实际调用的 provider。
    默认使用 rembg 本地执行。
    """

    INPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "process"
    _node_type = "RemoveBG"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        """通过能力路由调用去背景"""
        if ctx.router is None:
            raise ValueError("RemoveBG 需要 router（能力路由器）")

        image = inputs.get("image")
        if image is None:
            raise ValueError("RemoveBG 需要 image 输入")

        payload = {"image": image}

        result = await ctx.router.route(Capability.REMOVE_BG, payload)

        output_image = result.get("image")
        if output_image is None:
            raise ValueError("remove_bg provider 未返回图片")

        ctx.log("去背景完成")
        return {"image": output_image}
