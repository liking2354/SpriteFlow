"""DirectionVariant 节点 — 方向变体生成（模板驱动）

管道阶段 2：接收上游角色母版图，套用方向/职业模板生成变体。
合并 FourDirection + ClassDerive。
"""

from __future__ import annotations

import asyncio

from ..engine.node import Node
from ..engine.types import PortType, Str, Seed
from ..providers.base import Capability


class DirectionVariantNode(Node):
    """方向变体节点（模板驱动）

    输入：角色母版图（来自上游 CharacterMaster）
    输出：各方向/职业变体的精灵图
    """

    INPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    PARAMS = [
        Str("template_ids", required=True),
        Str("size", default="2k"),
        Seed("seed"),
        Str("watermark", default="false", choices=["true", "false"]),
        Str("output_format", default="png"),
    ]
    OUTPUTS: dict[str, PortType] = {
        "images": PortType.IMAGE_BATCH,
        "down": PortType.IMAGE,
        "up": PortType.IMAGE,
        "left": PortType.IMAGE,
        "right": PortType.IMAGE,
    }
    CATEGORY = "pipeline"
    _node_type = "DirectionVariant"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("DirectionVariant 需要 router")
        if ctx.template_db is None:
            raise ValueError("DirectionVariant 需要 template_db")

        master_image = inputs.get("image")
        if master_image is None:
            raise ValueError("DirectionVariant 需要 image 输入（来自上游角色母版）")

        from ..templates.builder import assemble_prompt

        # 解析 template_ids
        raw_ids = params.get("template_ids", "")
        template_ids = [tid.strip() for tid in raw_ids.split(",") if tid.strip()]
        if not template_ids:
            raise ValueError("DirectionVariant 需要至少一个 template_id")

        slot_values = params.get("slot_values") or {}
        size = params.get("size", "2k")
        seed = params.get("seed")
        watermark = str(params.get("watermark", "false")).lower() == "true"
        output_format = params.get("output_format", "png")

        # 记录执行输入快照（供前端审查 prompt）
        inputs_snapshot: dict[str, Any] = {
            "template_ids": template_ids,
            "slot_values": slot_values,
            "size": size,
            "variants": [],
        }

        async def _gen_variant(tid: str):
            t = await ctx.template_db.get(tid)
            if t is None:
                raise ValueError(f"模板不存在: {tid}")

            # 拼装该模板的 prompt
            prompt = await assemble_prompt(ctx.template_db, [tid], slot_values)
            final_prompt = f"same character design, proportions, and art style as reference image. {prompt}"

            payload = {
                "prompt": final_prompt,
                "image": master_image,
                "size": size,
                "seed": seed + hash(tid) if seed else None,
                "watermark": watermark,
                "output_format": output_format,
                "response_format": "url",
            }
            result = await ctx.router.route(Capability.FOUR_VIEW, payload)
            img = result.get("image")
            if img is None:
                raise ValueError(f"模板 '{t.name}' 生成失败：未返回图片")
            ctx.log(f"变体 '{t.name}' 生成完成: {img.size}")
            return t.name, img, final_prompt

        tasks = [_gen_variant(tid) for tid in template_ids]
        results = await asyncio.gather(*tasks)

        outputs: dict = {"images": []}
        # 映射方向名到输出端口
        direction_map = {
            "down": "down", "up": "up", "left": "left", "right": "right",
            "向下": "down", "向上": "up", "向左": "left", "向右": "right",
        }
        for name, img, final_prompt in results:
            outputs["images"].append(img)
            inputs_snapshot["variants"].append({"name": name, "prompt": final_prompt})
            for keyword, port in direction_map.items():
                if keyword.lower() in name.lower():
                    outputs[port] = img
                    break

        ctx.set_node_inputs(self.node_id, inputs_snapshot)
        ctx.log(f"方向变体生成完成: {len(outputs['images'])} 个变体")
        return outputs
