"""CharacterMaster 节点 — 角色母版生成（模板驱动）

管道阶段 1：template_ids + slot_values → prompt 拼装 → 文生图 → 去背景 → 精灵对齐
"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType, Str, Seed, Int
from ..providers.base import Capability


class CharacterMasterNode(Node):
    """角色母版节点（模板驱动）

    输入：无（从模板系统加载数据拼装 prompt）
    输出：对齐后的角色精灵图
    """

    INPUTS: dict[str, PortType] = {}
    PARAMS = [
        Str("template_ids", required=True),
        Str("style_prompt", default=""),
        Str("size", default="2k"),
        Int("canvas_width", default=512),
        Int("canvas_height", default=512),
        Int("target_width", default=448),
        Int("target_height", default=480),
        Int("detect_threshold", default=32),
        Int("padding", default=8),
        Seed("seed"),
        Str("watermark", default="false", choices=["true", "false"]),
        Str("output_format", default="png"),
    ]
    OUTPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    CATEGORY = "pipeline"
    _node_type = "CharacterMaster"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("CharacterMaster 需要 router")
        if ctx.template_db is None:
            raise ValueError("CharacterMaster 需要 template_db")

        from ..templates.builder import assemble_prompt
        from ..engine.sprite_aligner import SpriteAligner

        # 1. 解析 template_ids 和 slot_values
        raw_ids = params.get("template_ids", "")
        template_ids = [tid.strip() for tid in raw_ids.split(",") if tid.strip()]
        if not template_ids:
            raise ValueError("CharacterMaster 需要至少一个 template_id")

        slot_values = params.get("slot_values") or {}

        # 2. 拼装 prompt
        prompt = await assemble_prompt(ctx.template_db, template_ids, slot_values)

        style = params.get("style_prompt", "").strip()
        if style:
            prompt += f"\n\n{style}"

        ctx.log(f"角色母版 prompt 拼装完成: {len(template_ids)} 个模板")

        # 记录执行输入快照
        ctx.set_node_inputs(self.node_id, {
            "prompt": prompt,
            "template_ids": template_ids,
            "slot_values": slot_values,
            "style_prompt": style,
            "size": params.get("size", "2k"),
        })

        # 3. 文生图
        size = params.get("size", "2k")
        seed = params.get("seed")
        watermark = str(params.get("watermark", "false")).lower() == "true"

        t2i_payload = {
            "prompt": prompt,
            "size": size,
            "seed": seed,
            "watermark": watermark,
            "output_format": params.get("output_format", "png"),
            "response_format": "url",
        }
        t2i_result = await ctx.router.route(Capability.CHARACTER_MASTER, t2i_payload)
        image = t2i_result.get("image")
        if image is None:
            raise ValueError("Text2Img 未返回图片")

        ctx.log(f"角色母版生成完成: {image.size}")

        # 4. 去背景
        rbg_result = await ctx.router.route(Capability.REMOVE_BG, {"image": image})
        image = rbg_result.get("image", image)
        ctx.log("去背景完成")

        # 5. 精灵对齐
        aligned = SpriteAligner.align(
            image=image,
            canvas_width=int(params.get("canvas_width", 512)),
            canvas_height=int(params.get("canvas_height", 512)),
            target_width=int(params.get("target_width", 448)),
            target_height=int(params.get("target_height", 480)),
            detect_threshold=int(params.get("detect_threshold", 32)),
            padding=int(params.get("padding", 8)),
            auto_center=True,
            auto_crop=True,
            bottom_align=True,
        )
        ctx.log(f"精灵对齐完成: {aligned.size}")

        return {"image": aligned}
