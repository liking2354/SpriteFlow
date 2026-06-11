"""CharacterMaster 节点 — 角色母版生成（模板驱动）

管道阶段 1：template_ids + slot_values → prompt 拼装 → 文生图 → [去背景?]

参数分类：
  一类（系统参数）：enable_remove_bg 去背景开关
  二类（模板参数）：template_ids + slot_values，按模板 Slots 动态展示
"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType, Str, Seed
from ..providers.base import Capability


def _parse_bool(params: dict, key: str, default: bool = False) -> bool:
    """解析布尔型参数，兼容 bool / 'true'/'false' 字符串"""
    val = params.get(key, default)
    if isinstance(val, bool):
        return val
    return str(val).lower() == "true"


class CharacterMasterNode(Node):
    """角色母版节点（模板驱动）

    输入：无（从模板系统加载数据拼装 prompt）
    输出：角色精灵图（保持 AI 生成原图尺寸）

    系统参数：
      enable_remove_bg    — 去背景开关（默认关闭）
    模板参数：
      template_ids + slot_values → assemble_prompt 拼装
    """

    INPUTS: dict[str, PortType] = {}
    PARAMS = [
        # ── 系统开关 ──
        Str("enable_remove_bg", default="false", choices=["true", "false"]),
        # ── 模板输入 ──
        Str("template_ids", required=True),
        Str("style_prompt", default=""),
        # ── 生成参数 ──
        Str("size", default="2k"),
        Str("watermark", default="false", choices=["true", "false"]),
        Str("output_format", default="png"),
        Seed("seed"),
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

        # ── 1. 解析 template_ids 和 slot_values ──
        raw_ids = params.get("template_ids", "")
        template_ids = [tid.strip() for tid in raw_ids.split(",") if tid.strip()]
        if not template_ids:
            raise ValueError("CharacterMaster 需要至少一个 template_id")

        slot_values = params.get("slot_values") or {}

        # ── 2. 拼装 prompt ──
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

        # ── 3. 文生图 ──
        size = params.get("size", "2k")
        seed = params.get("seed")
        watermark = _parse_bool(params, "watermark")

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

        # ── 4. 去背景（可开关，默认关闭）──
        if _parse_bool(params, "enable_remove_bg", default=False):
            rbg_result = await ctx.router.route(Capability.REMOVE_BG, {"image": image})
            image = rbg_result.get("image", image)
            ctx.log("去背景完成")
        else:
            ctx.log("跳过去背景")

        return {"image": image}
