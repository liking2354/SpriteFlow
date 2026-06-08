"""ImageFusion 节点 — 图像融合（管线业务节点，模板驱动）

管道阶段 5：接收上游多张素材图，融合为一张完整图。
管线包装 MultiImageFusion 核心能力。
"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType, Str, Seed
from ..providers.base import Capability


class ImageFusionNode(Node):
    """图像融合节点（管线业务节点）

    输入：多张图（来自上游管线节点）
    输出：融合后的单张图
    """

    INPUTS: dict[str, PortType] = {
        "images": PortType.IMAGE_BATCH,
    }
    PARAMS = [
        Str("template_ids", default=""),
        Str("size", default="2k"),
        Seed("seed"),
        Str("watermark", default="false", choices=["true", "false"]),
        Str("output_format", default="png"),
    ]
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "pipeline"
    _node_type = "ImageFusion"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("ImageFusion 需要 router")

        from ..templates.builder import assemble_prompt

        # 收集参考图
        refs: list = []
        batch = inputs.get("images")
        if batch:
            if isinstance(batch, list):
                refs.extend(batch)
            else:
                refs.append(batch)

        if len(refs) < 2:
            raise ValueError(
                f"ImageFusion 需要至少 2 张参考图，当前只有 {len(refs)} 张"
            )

        # 拼装 prompt
        raw_ids = params.get("template_ids", "")
        template_ids = [tid.strip() for tid in raw_ids.split(",") if tid.strip()]
        slot_values = params.get("slot_values") or {}

        prompt = ""
        if template_ids and ctx.template_db is not None:
            prompt = await assemble_prompt(ctx.template_db, template_ids, slot_values)

        size = params.get("size", "2k")
        seed = params.get("seed")
        watermark = str(params.get("watermark", "false")).lower() == "true"

        payload = {
            "prompt": prompt,
            "image": refs,
            "size": size,
            "seed": seed,
            "watermark": watermark,
            "output_format": params.get("output_format", "png"),
            "response_format": "url",
        }

        result = await ctx.router.route(Capability.MULTI_IMAGE_FUSION, payload)
        image = result.get("image")
        if image is None:
            raise ValueError("multi_image_fusion provider 未返回图片")

        ctx.log(f"图像融合完成: refs={len(refs)}")
        return {"image": image}
