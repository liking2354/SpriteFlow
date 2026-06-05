"""Rembg Provider — 本地去背景"""

from __future__ import annotations

from typing import Any

from PIL import Image

from .base import Provider, Capability, Credential


class RembgProvider(Provider):
    """本地 rembg 去背景 Provider

    无需 API Key，使用 rembg 库在本地执行。
    """

    name = "rembg"
    capabilities = {Capability.REMOVE_BG}

    async def invoke(
        self,
        cap: Capability,
        payload: dict[str, Any],
        cred: Credential,
    ) -> dict[str, Any]:
        """执行去背景"""
        if cap != Capability.REMOVE_BG:
            raise ValueError(f"RembgProvider 不支持能力: {cap}")

        import io

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

        result_image = self._remove_background(image)
        return {"image": result_image}

    def _remove_background(self, image: Image.Image) -> Image.Image:
        """使用 rembg 去除背景"""
        try:
            from rembg import remove
        except ImportError:
            raise ImportError("rembg 未安装，请执行: pip install rembg")

        # rembg 需要 RGB 或 RGBA 输入
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")

        output = remove(image)
        return output.convert("RGBA")
