"""SkillVFX 节点 — 技能特效生成（模板驱动）

管道阶段 4：接收上游角色图（可选），生成技能特效序列帧。
"""

from __future__ import annotations

import asyncio

from ..engine.node import Node
from ..engine.types import PortType, Str, Seed, Int
from ..providers.base import Capability


class SkillVFXNode(Node):
    """技能特效节点（模板驱动）

    输入：角色图（可选，用于生成配合角色动作的特效）
    输出：特效序列帧
    """

    INPUTS: dict[str, PortType] = {"image": PortType.IMAGE}
    PARAMS = [
        Str("template_ids", required=True),
        Int("max_images", default=8),
        Str("size", default="2k"),
        Seed("seed"),
        Str("watermark", default="false", choices=["true", "false"]),
        Str("output_format", default="png"),
    ]
    OUTPUTS: dict[str, PortType] = {"images": PortType.IMAGE_BATCH}
    CATEGORY = "pipeline"
    _node_type = "SkillVFX"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("SkillVFX 需要 router")
        if ctx.template_db is None:
            raise ValueError("SkillVFX 需要 template_db")

        from ..templates.builder import assemble_prompt

        # 解析 template_ids
        raw_ids = params.get("template_ids", "")
        template_ids = [tid.strip() for tid in raw_ids.split(",") if tid.strip()]
        if not template_ids:
            raise ValueError("SkillVFX 需要至少一个 template_id")

        slot_values = params.get("slot_values") or {}
        ref_image = inputs.get("image")
        size = params.get("size", "2k")
        seed = params.get("seed")
        watermark = str(params.get("watermark", "false")).lower() == "true"
        max_images = int(params.get("max_images", 8))
        output_format = params.get("output_format", "png")

        async def _gen_vfx(tid: str):
            t = await ctx.template_db.get(tid)
            if t is None:
                raise ValueError(f"模板不存在: {tid}")

            # 拼装该模板的 prompt
            prompt = await assemble_prompt(ctx.template_db, [tid], slot_values)

            if ref_image is not None:
                # 有角色参考图时使用 SequentialImages
                payload = {
                    "prompt": prompt,
                    "image": ref_image,
                    "max_images": max_images,
                    "size": size,
                    "seed": seed + hash(tid) if seed else None,
                    "watermark": watermark,
                    "output_format": output_format,
                    "response_format": "url",
                }
                result = await ctx.router.route(Capability.SEQUENTIAL_IMAGES, payload)
            else:
                # 纯特效（无角色参考图）多次调用 Text2Img
                t2i_payload = {
                    "prompt": prompt,
                    "size": size,
                    "seed": seed + hash(tid) + i if seed else None,
                    "watermark": watermark,
                    "output_format": output_format,
                    "response_format": "url",
                }
                images = []
                for i in range(max_images):
                    t2i_payload["seed"] = seed + hash(tid) + i if seed else None
                    t2i_result = await ctx.router.route(Capability.TEXT2IMG, t2i_payload)
                    img = t2i_result.get("image")
                    if img:
                        images.append(img)
                result = {"images": images}

            images = result.get("images") or []
            if not images:
                raise ValueError(f"特效 '{t.name}' 生成失败：未返回图片")

            ctx.log(f"特效 '{t.name}' 生成完成: {len(images)} 帧")
            return images

        tasks = [_gen_vfx(tid) for tid in template_ids]
        results = await asyncio.gather(*tasks)

        all_images = []
        for imgs in results:
            all_images.extend(imgs)

        ctx.log(f"技能特效生成完成: {len(template_ids)} 个特效, {len(all_images)} 帧")
        return {"images": all_images}
