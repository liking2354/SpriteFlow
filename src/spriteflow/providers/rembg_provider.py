"""Rembg Provider — 统一的本地去背景入口

所有后端抠图请求均通过 CapabilityRouter 路由到此 Provider。
支持通过 payload 参数选择模型 session：
  - 不传 session（默认）：使用 rembg 默认模型
  - session="u2net"：使用 u2net 模型（适用于需要更高精度的场景）

CPU 密集操作通过 asyncio.to_thread 放入线程池执行，不阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

from PIL import Image

from .base import Provider, Capability, Credential


class RembgProvider(Provider):
    """统一的本地 rembg 去背景 Provider

    无需 API Key，使用 rembg 库在本地执行。
    所有后端抠图功能的唯一入口，方便后续统一调整或扩展。
    """

    name = "rembg"
    capabilities = {Capability.REMOVE_BG}

    async def invoke(
        self,
        cap: Capability,
        payload: dict[str, Any],
        cred: Credential,
    ) -> dict[str, Any]:
        """执行去背景（CPU 密集操作在线程池中执行）"""
        if cap != Capability.REMOVE_BG:
            raise ValueError(f"RembgProvider 不支持能力: {cap}")

        image = payload.get("image")

        # 兼容字节流：传入 image_bytes 也能工作
        if image is None:
            image_bytes = payload.get("image_bytes")
            if image_bytes is not None:
                image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

        if image is None:
            raise ValueError("payload 缺少 'image' 或 'image_bytes' 字段")

        if not isinstance(image, Image.Image):
            raise ValueError(f"'image' 必须是 PIL.Image，实际类型: {type(image)}")

        # 可选：指定 rembg session 模型（如 "u2net"）
        session_name = payload.get("session")

        # 可选：edge matting 精细修边
        alpha_matting = payload.get("alpha_matting", False)

        # CPU 密集操作放入线程池，避免阻塞事件循环
        result_image = await asyncio.to_thread(
            self._remove_background, image, session_name, alpha_matting
        )
        return {"image": result_image}

    def _remove_background(
        self,
        image: Image.Image,
        session_name: str | None = None,
        alpha_matting: bool = False,
    ) -> Image.Image:
        """使用 rembg 去除背景（同步，在线程池中调用）

        Args:
            image: 输入图片
            session_name: rembg 模型名称，如 "u2net"。None 则使用默认模型。
            alpha_matting: 是否启用边缘精细修边处理
        """
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
