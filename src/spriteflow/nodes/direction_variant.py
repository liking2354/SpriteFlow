"""DirectionVariant 节点 — 方向变体生成（IMG2IMG）

管道阶段 2：接收上游角色母版图，根据方向模板生成单个朝向的角色图。
每个节点负责一个方向，产出单张图。典型用法：每个 DirectionVariant
选一个方向模板，下游连一个 AnimationSprite 选动作模板。
"""

from __future__ import annotations

from typing import Any

from ..engine.node import Node
from ..engine.types import PortType, Str, Seed
from ..providers.base import Capability


class DirectionVariantNode(Node):
    """方向变体节点

    输入：角色母版图（来自上游 CharacterMaster）
    输出：单张方向变体图
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
        "image": PortType.IMAGE,          # 主输出：单张方向图，连 AnimationSprite
        "images": PortType.IMAGE_BATCH,   # 批量输出：兼容 GalleryViewer
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

        raw_ids = params.get("template_ids", "")
        template_ids = [tid.strip() for tid in raw_ids.split(",") if tid.strip()]
        if not template_ids:
            raise ValueError("DirectionVariant 需要至少一个 template_id")

        slot_values = params.get("slot_values") or {}
        size = params.get("size", "2k")
        seed = params.get("seed")
        watermark = str(params.get("watermark", "false")).lower() == "true"
        output_format = params.get("output_format", "png")

        from ..templates.builder import assemble_prompt

        inputs_snapshot: dict[str, Any] = {
            "template_ids": template_ids,
            "slot_values": slot_values,
            "size": size,
            "variants": [],
        }

        all_images: list = []
        for tid in template_ids:
            t = await ctx.template_db.get(tid)
            if t is None:
                raise ValueError(f"模板不存在: {tid}")

            prompt = await assemble_prompt(ctx.template_db, [tid], slot_values)
            final_prompt = (
                f"same character design, proportions, and art style "
                f"as reference image. {prompt}"
            )

            payload = {
                "prompt": final_prompt,
                "image": master_image,
                "size": size,
                "seed": seed + hash(tid) if seed else None,
                "watermark": watermark,
                "output_format": output_format,
                "response_format": "url",
            }
            result = await ctx.router.route(Capability.IMG2IMG, payload)
            img = result.get("image")
            if img is None:
                raise ValueError(f"模板 '{t.name}' 生成失败：未返回图片")

            ctx.log(f"方向变体 '{t.name}' 生成完成: {img.size}")
            all_images.append(img)
            inputs_snapshot["variants"].append({
                "name": t.name,
                "prompt": final_prompt,
            })

        ctx.set_node_inputs(self.node_id, inputs_snapshot)
        ctx.log(f"方向变体生成完成: {len(all_images)} 个变体")
        return {"image": all_images[0], "images": all_images}
