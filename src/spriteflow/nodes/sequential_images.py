"""SequentialImages 节点 — 多参考图生组图（一次出 N 张关联图）

典型场景：参考一张角色图，一次生成 8 张同角色不同朝向 / 不同动作。
非常适合精灵表 8 方向生成（替代 Fanout + 8 次单独 Img2Img 调用）。

Seedream 协议：
  sequential_image_generation: "auto"
  sequential_image_generation_options.max_images: N
"""

from __future__ import annotations

from ..engine.node import Node
from ..engine.types import PortType
from ..providers.base import Capability


class SequentialImagesNode(Node):
    """多参考图生组图节点 — 输出 IMAGE_BATCH"""

    INPUTS: dict[str, PortType] = {
        "image": PortType.IMAGE,             # 主参考图（可选）
        "extra_images": PortType.IMAGE_BATCH, # 额外参考图（可选）
    }
    OUTPUTS: dict[str, PortType] = {
        "images": PortType.IMAGE_BATCH,
        "first": PortType.IMAGE,
    }
    CATEGORY = "generate"
    _node_type = "SequentialImages"

    async def execute(self, inputs: dict, params: dict, ctx) -> dict:
        if ctx.router is None:
            raise ValueError("SequentialImages 需要 router")

        # 收集参考图（可无）
        refs: list = []
        if (main := inputs.get("image")) is not None:
            refs.append(main)
        if (extras := inputs.get("extra_images")) is not None:
            if isinstance(extras, list):
                refs.extend(extras)
            else:
                refs.append(extras)
        for u in params.get("image_urls") or []:
            refs.append(u)

        max_images = int(params.get("max_images", 4))

        payload = {
            "prompt": params.get("prompt", ""),
            "max_images": max_images,
            "size": params.get("size", "2K"),
            "seed": params.get("seed"),
            "watermark": params.get("watermark", False),
            "output_format": params.get("output_format", "png"),
            "response_format": params.get("response_format", "url"),
            "stream": bool(params.get("stream", False)),
        }
        if refs:
            payload["image"] = refs if len(refs) > 1 else refs[0]

        # 流式时把进度透到 ctx.log
        if payload["stream"]:
            async def _on_event(evt: dict) -> None:
                etype = evt.get("type", "")
                if etype == "image_generation.partial_succeeded":
                    idx = evt.get("image_index")
                    ctx.log(f"  [stream] 收到第 {idx} 张图: {evt.get('size')}")
                elif etype == "image_generation.completed":
                    ctx.log(f"  [stream] 完成 usage={evt.get('usage')}")
            payload["on_event"] = _on_event

        result = await ctx.router.route(Capability.SEQUENTIAL_IMAGES, payload)

        images = result.get("images") or []
        if not images:
            raise ValueError("sequential_images provider 未返回任何图片")

        ctx.log(
            f"组图生成完成: 期望 {max_images} 张，实际 {len(images)} 张，"
            f"refs={len(refs)}, prompt='{payload['prompt'][:40]}...'"
        )
        return {"images": images, "first": images[0]}
