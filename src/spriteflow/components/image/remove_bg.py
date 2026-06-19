"""
RemoveBG 组件 — AI 抠图去背景

基于 rembg 本地模型，支持多种模型选择和 Alpha 修边精细处理。
默认配置：通用首选（isnet-general-use）+ Alpha 修边选中。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from typing import Any

import httpx
from PIL import Image

from ..base import Component, ComponentMeta
from ..utils import save_image_local, download_image

logger = logging.getLogger(__name__)

SESSION_CHOICES = [
    {"value": "isnet-general-use", "label": "通用首选 (isnet)"},
    {"value": "u2net", "label": "u2net"},
    {"value": "u2net_human_seg", "label": "人像分割 (u2net_human_seg)"},
    {"value": "silueta", "label": "silueta"},
    {"value": "", "label": "默认模型"},
]


def _remove_background(
    image: Image.Image,
    session_name: str | None = None,
    alpha_matting: bool = False,
) -> Image.Image:
    """使用 rembg 去除背景（同步，在线程池中调用）"""
    try:
        from rembg import remove
    except ImportError:
        raise ImportError("rembg 未安装，请执行: pip install rembg")

    if session_name:
        from rembg.session_factory import new_session
        session = new_session(session_name)
    else:
        session = None

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    kwargs = {}
    if alpha_matting:
        kwargs.update(
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )

    output = remove(image, session=session, **kwargs)
    return output.convert("RGBA")


async def _download_image(url: str) -> Image.Image:
    """从 URL 下载图片（本地 workflow runs 文件直接读取，避免 HTTP 回环死锁）"""
    # 检测是否为本地 workflow runs 输出 URL，避免同一进程 HTTP 回环导致死锁
    import re as _re
    _local_match = _re.search(r"/api/workflow/runs/([^/]+)/outputs/(.+)", url)
    if _local_match:
        from spriteflow.config import settings
        run_id, filename = _local_match.group(1), _local_match.group(2)
        filepath = settings.workflow_runs_dir / run_id / "outputs" / filename
        if filepath.is_file():
            return Image.open(filepath).convert("RGBA")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")


async def _upload_image(image: Image.Image, filename_prefix: str = "remove_bg") -> str:
    """上传图片到存储，返回可访问的 URL"""
    from spriteflow.api.deps import get_storage
    from spriteflow.storage.base import StoragePrefix

    storage = get_storage()

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data = buf.getvalue()

    content_hash = hashlib.sha256(data).hexdigest()[:32]
    file_key = f"{filename_prefix}_{content_hash}.png"

    uri = await storage.upload(file_key, data, prefix=StoragePrefix.AI_PROCESSED, content_type="image/png")

    try:
        url = await storage.get_presigned_url(uri)
    except Exception:
        url = uri

    logger.info("[RemoveBG] uploaded: %s", url[:120])
    return url


class RemoveBGComponent(Component):
    """AI 抠图去背景组件"""

    @property
    def meta(self) -> ComponentMeta:
        return ComponentMeta(
            component_id="image-remove-bg",
            display_name="AI抠图去背景",
            category="image",
            subcategory="image",
            description="使用 AI 模型自动去除图片背景，支持多种模型和精细 Alpha 修边处理",
            version="1.0.0",
            icon="✂️",
            output_type="image_url",
            credential_schema={},
            input_schema={
                "image_url": {
                    "type": "string",
                    "title": "输入图片",
                    "description": "待去背景的图片 URL（支持上游连线输入）",
                    "format": "uri",
                },
                "session": {
                    "type": "string",
                    "title": "AI 模型",
                    "description": "选择去背景模型",
                    "enum": [s["value"] for s in SESSION_CHOICES],
                    "enumNames": [s["label"] for s in SESSION_CHOICES],
                    "default": "isnet-general-use",
                },
                "alpha_matting": {
                    "type": "boolean",
                    "title": "Alpha 修边",
                    "description": "开启精细边缘修边处理（推荐）",
                    "default": True,
                },
            },
            input_required=["image_url"],
        )

    async def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        image_url = inputs.get("image_url", "")
        if not image_url:
            errors.append("请提供输入图片（image_url 不能为空）")
        return errors

    async def execute(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        image_url = inputs.get("image_url", "")
        if not image_url:
            raise ValueError("缺少输入图片 URL")

        # 合并 inputs 和 params（workflow 中两者可能相同）
        session_name = params.get("session") or inputs.get("session") or "isnet-general-use"
        if session_name == "":
            session_name = None  # 使用 rembg 默认模型

        alpha_matting_raw = params.get("alpha_matting") or inputs.get("alpha_matting")
        if isinstance(alpha_matting_raw, bool):
            alpha_matting = alpha_matting_raw
        else:
            alpha_matting = str(alpha_matting_raw).lower() == "true" if alpha_matting_raw is not None else True

        logger.info(
            "[RemoveBG] image=%s session=%s alpha_matting=%s",
            image_url[:120], session_name, alpha_matting,
        )

        # 1. 下载图片
        image = await download_image(image_url)
        logger.info("[RemoveBG] downloaded: %dx%d", image.width, image.height)

        # 2. 去背景（CPU 密集操作放线程池）
        result = await asyncio.to_thread(
            _remove_background, image, session_name, alpha_matting,
        )
        logger.info("[RemoveBG] processed: %dx%d", result.width, result.height)

        # 3. 保存结果到本地
        url = await save_image_local(result)
        logger.info("[RemoveBG] done: %s", url[:120])

        return {
            "outputs": [
                {"type": "image_url", "value": url},
            ],
        }
