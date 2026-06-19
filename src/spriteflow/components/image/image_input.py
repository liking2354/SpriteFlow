"""
ImageInput 组件 — 图片输入/展示节点

用于在工作流中引入输入图片（素材库选择、本地上传或上游节点输入），
作为透传节点将 image_url 传递给下游消费。
"""

from __future__ import annotations

import logging
from typing import Any

from ..base import Component, ComponentMeta

logger = logging.getLogger(__name__)


class ImageInputComponent(Component):
    """图片输入组件 — 透传 image_url"""

    @property
    def meta(self) -> ComponentMeta:
        return ComponentMeta(
            component_id="image-input",
            display_name="图片输入",
            category="image",
            subcategory="image",
            description="工作流图片入口节点，支持素材库选择、本地上传或上游输入。可通过 image_index 选择精灵裁剪等批量输出的第 N 张图（0=第一张）",
            version="1.0.0",
            icon="🖼️",
            output_type="image_url",
            credential_schema={},
            input_schema={
                "image_url": {
                    "type": "string",
                    "title": "输入图片",
                    "description": "从上游节点输入、素材库选择或本地上传的图片 URL。连接精灵裁剪节点时自动取 outputs[image_index]",
                    "format": "uri",
                },
                "image_index": {
                    "type": "integer",
                    "title": "图片索引",
                    "description": "当上游为精灵裁剪等多图输出节点时，选择使用第几张图片（0=第一张，1=第二张，...)",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            input_required=["image_url"],
        )

    async def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        image_url = inputs.get("image_url", "")
        if not image_url:
            errors.append("请选择或上传输入图片（image_url 不能为空）")
        return errors

    async def execute(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        image_url = inputs.get("image_url", "")
        if not image_url:
            raise ValueError("请输入图片 URL 或通过上游节点连线传入图片")

        # 支持多图输出时选择特定索引
        # 优先使用上游精灵裁剪节点通过 meta.all_urls 注入的全部 URL
        image_index_raw = params.get("image_index") if params.get("image_index") is not None else inputs.get("image_index")
        if image_index_raw is None:
            image_index_raw = 0
        try:
            image_index = int(image_index_raw)
        except (ValueError, TypeError):
            image_index = 0

        # 1. 优先从上游节点 meta 注入的 all_urls 中获取全部 URL
        all_urls = inputs.get("all_urls") or params.get("all_urls") or ""
        if all_urls:
            urls = [u.strip() for u in str(all_urls).split(",") if u.strip()]
            idx = max(0, min(image_index, len(urls) - 1))
            selected_url = urls[idx]
            logger.info("[ImageInput] selected index %d/%d from all_urls: %s", idx, len(urls), selected_url[:120])
        else:
            # 2. 回退：检查 image_url 本身是否为逗号分隔的多 URL
            urls = [u.strip() for u in str(image_url).split(",") if u.strip()]
            if len(urls) > 1:
                idx = max(0, min(image_index, len(urls) - 1))
                selected_url = urls[idx]
                logger.info("[ImageInput] selected index %d/%d from image_url: %s", idx, len(urls), selected_url[:120])
            else:
                # 3. 单张图片直接透传
                selected_url = image_url
                logger.info("[ImageInput] pass-through: %s", selected_url[:120])

        return {
            "outputs": [
                {"type": "image_url", "value": selected_url},
            ],
        }
