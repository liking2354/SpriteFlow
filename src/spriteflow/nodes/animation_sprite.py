"""AnimationSprite 节点 — 动作动画生成（模板驱动）

管道阶段 3：接收上游角色图，套用动作模板生成动画序列帧。
合并 ActionDerive + EquipmentDerive。
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..engine.node import Node
from ..engine.types import PortType, Str, Seed, Int
from ..providers.base import Capability


class AnimationSpriteNode(Node):
    """动画精灵节点（模板驱动）

    输入：角色图（来自上游）
    输出：各动作的序列帧精灵图
    """

    INPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    PARAMS = [
        Str("template_ids", required=True),
        Int("max_images", default=1),
        Str("size", default="2k"),
        Seed("seed"),
        Str("watermark", default="false", choices=["true", "false"]),
        Str("output_format", default="png"),
    ]
    OUTPUTS: dict[str, PortType] = {"images": PortType.IMAGE_BATCH}
    CATEGORY = "pipeline"
    _node_type = "AnimationSprite"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("AnimationSprite 需要 router")
        if ctx.template_db is None:
            raise ValueError("AnimationSprite 需要 template_db")

        ref_image = inputs.get("image")
        if ref_image is None:
            raise ValueError("AnimationSprite 需要 image 输入")
        # 兼容上游 IMAGE_BATCH 连接：取第一张图
        if isinstance(ref_image, list):
            ref_image = ref_image[0] if ref_image else None
            if ref_image is None:
                raise ValueError("AnimationSprite 收到空列表输入")

        from ..templates.builder import assemble_prompt

        # 解析 template_ids
        raw_ids = params.get("template_ids", "")
        template_ids = [tid.strip() for tid in raw_ids.split(",") if tid.strip()]
        if not template_ids:
            raise ValueError("AnimationSprite 需要至少一个 template_id")

        slot_values = params.get("slot_values") or {}
        size = params.get("size", "2k")
        seed = params.get("seed")
        watermark = str(params.get("watermark", "false")).lower() == "true"
        max_images = int(params.get("max_images", 1))
        output_format = params.get("output_format", "png")

        # 记录执行输入快照（供前端审查 prompt）
        inputs_snapshot: dict[str, Any] = {
            "template_ids": template_ids,
            "slot_values": slot_values,
            "size": size,
            "max_images": max_images,
            "prompts": [],
        }

        async def _gen_anim(tid: str):
            t = await ctx.template_db.get(tid)
            if t is None:
                raise ValueError(f"模板不存在: {tid}")

            # 拼装该模板的 prompt
            prompt = await assemble_prompt(ctx.template_db, [tid], slot_values)

            if max_images > 1:
                # 多帧生成（SequentialImages）
                payload = {
                    "prompt": f"same character design, proportions, and art style as reference image. {prompt}",
                    "image": ref_image,
                    "max_images": max_images,
                    "size": size,
                    "seed": seed + hash(tid) if seed else None,
                    "watermark": watermark,
                    "output_format": output_format,
                    "response_format": "url",
                }
                result = await ctx.router.route(Capability.SEQUENTIAL_IMAGES, payload)
                images = result.get("images") or []
            else:
                # 单帧（Img2Img）
                payload = {
                    "prompt": f"same character design, proportions, and art style as reference image. {prompt}",
                    "image": ref_image,
                    "size": size,
                    "seed": seed + hash(tid) if seed else None,
                    "watermark": watermark,
                    "output_format": output_format,
                    "response_format": "url",
                }
                result = await ctx.router.route(Capability.IMG2IMG, payload)
                img = result.get("image")
                images = [img] if img else []

            ctx.log(f"动画 '{t.name}' 生成完成: {len(images)} 帧")
            return t.name, prompt, images

        tasks = [_gen_anim(tid) for tid in template_ids]
        results = await asyncio.gather(*tasks)

        all_images = []
        for name, final_prompt, imgs in results:
            all_images.extend(imgs)
            inputs_snapshot["prompts"].append({"name": name, "prompt": final_prompt})

        ctx.set_node_inputs(self.node_id, inputs_snapshot)
        ctx.log(f"动画精灵生成完成: {len(template_ids)} 个动作, {len(all_images)} 帧")
        return {"images": all_images}
