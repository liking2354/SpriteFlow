"""火山引擎 AI MediaKit 图像处理 Provider

使用老版 volcengine SDK (volcengine.visual.VisualService) 实现：
  - 图像画质增强 (enhance_photo_v2)
  - 图像擦除修复 (image_inpaint)
  - 图像背景移除 (human_segment / general_segment)
  - 图像智能裁剪 (image_cut)
  - 智能扩图 (image_outpaint)

集智瘦身 / 图像缩放通过 MediaKit Bearer Token HTTP API 调用。
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

import logging

logger = logging.getLogger(__name__)

from .base import Provider, Capability, Credential

# ---------------------------------------------------------------------------
# 懒加载 VisualService，避免 import 时依赖未安装
# ---------------------------------------------------------------------------

_visual_svc = None


def _get_visual_service(ak: str, sk: str):
    global _visual_svc
    if _visual_svc is None:
        from volcengine.visual.VisualService import VisualService
        svc = VisualService()
        svc.set_ak(ak)
        svc.set_sk(sk)
        _visual_svc = svc
    return _visual_svc


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def _base64_to_bytes(b64_str: str) -> bytes:
    # 去掉可能的 data URI 前缀
    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    return base64.b64decode(b64_str)


def _download_image(url: str, timeout: int = 30) -> bytes:
    """下载图片并返回 bytes"""
    req = urllib.request.Request(url, headers={"User-Agent": "SpriteFlow/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _upload_result(result_bytes: bytes, storage, asset_id: str) -> str:
    """将处理结果写回存储，返回可访问的 URL"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.new_event_loop()
    try:
        coro = storage.upload(
            data=result_bytes,
            content_type="image/png",
            key_hint=f"processed/{asset_id}_{int(time.time())}.png",
        )
        future = asyncio.ensure_future(coro, loop=loop)
        return loop.run_until_complete(future)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Provider 实现
# ---------------------------------------------------------------------------


class VolcengineImageProvider(Provider):
    """火山引擎图像处理 Provider

    支持能力：
      - ENHANCE_PHOTO  图像画质增强
      - IMAGE_INPAINT   图像擦除修复
      - IMAGE_CUT       图像智能裁剪
      - IMAGE_OUTPAINT  智能扩图
      - SLIM_IMAGE      集智瘦身（HTTP Bearer Token API）
      - RESIZE_IMAGE    图像缩放（HTTP Bearer Token API）
    """

    name = "volcengine_image"
    capabilities = {
        Capability.ENHANCE_PHOTO,
        Capability.IMAGE_INPAINT,
        Capability.IMAGE_CUT,
        Capability.IMAGE_OUTPAINT,
        Capability.SLIM_IMAGE,
        Capability.RESIZE_IMAGE,
    }

    def __init__(self, ak: str = "", sk: str = "", mediakit_api_key: str = ""):
        # 优先使用传入参数，其次从 settings 读取
        from ..config import settings as _settings
        self.ak = ak or _settings.volc_access_key_id
        self.sk = sk or _settings.volc_secret_access_key
        self.mediakit_api_key = mediakit_api_key or _settings.volc_mediakit_api_key
        self._base_url = "https://mediakit.cn-beijing.volces.com/api/v1"

    async def invoke(
        self,
        cap: Capability,
        payload: dict[str, Any],
        cred: Credential,
    ) -> dict[str, Any]:
        # 凭证已在 __init__ 中从 settings 读取，无需从 cred 获取
        ak = self.ak
        sk = self.sk

        image_bytes = payload.get("image_bytes")
        image_url = payload.get("image_url", "")

        if not image_bytes and image_url:
            image_bytes = _download_image(image_url)

        if not image_bytes:
            raise ValueError("需要提供 image_bytes 或 image_url")

        if cap == Capability.ENHANCE_PHOTO:
            return await self._enhance_photo(ak, sk, image_bytes, payload)
        elif cap == Capability.IMAGE_INPAINT:
            return await self._image_inpaint(ak, sk, image_bytes, payload)
        elif cap == Capability.IMAGE_CUT:
            return await self._image_cut(ak, sk, image_bytes, payload)
        elif cap == Capability.IMAGE_OUTPAINT:
            return await self._image_outpaint(ak, sk, image_bytes, payload)
        elif cap == Capability.SLIM_IMAGE:
            return await self._slim_image(image_bytes, payload)
        elif cap == Capability.RESIZE_IMAGE:
            return await self._resize_image(image_bytes, payload)
        else:
            raise ValueError(f"不支持的能力: {cap}")

    # ------------------------------------------------------------------
    # SDK 封装 API
    # ------------------------------------------------------------------

    async def _enhance_photo(self, ak: str, sk: str, image_bytes: bytes, payload: dict) -> dict:
        """图像画质增强 — enhance_photo_v2 (req_key=lens_lqir)"""
        import asyncio

        svc = _get_visual_service(ak, sk)
        b64 = _image_to_base64(image_bytes)

        form = {
            "req_key": payload.get("req_key", "lqir"),  # lqir=画质增强
            "image_base64": b64,
            "return_url": 1,  # 返回 URL 而非 base64
        }
        if payload.get("longest_edge"):
            form["longest_edge"] = payload["longest_edge"]

        logger.info(f"[volc] enhance_photo_v2 req_key={form['req_key']}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: svc.enhance_photo_v2(form))

        image_url = result.get("data", {}).get("image", "")
        if not image_url and result.get("data", {}).get("image_base64"):
            img_bytes = _base64_to_bytes(result["data"]["image_base64"])
            return {"image_bytes": img_bytes, "raw": result}

        # 下载结果图
        img_bytes = _download_image(image_url) if image_url else b""
        return {"image_url": image_url, "image_bytes": img_bytes, "raw": result}

    async def _image_inpaint(self, ak: str, sk: str, image_bytes: bytes, payload: dict) -> dict:
        """图像擦除修复 — image_inpaint"""
        import asyncio

        svc = _get_visual_service(ak, sk)
        b64 = _image_to_base64(image_bytes)

        form = {
            "image_base64": b64,
        }
        # mask 可选：指定擦除区域，不传则自动检测修复区域
        if payload.get("mask_base64"):
            form["mask_base64"] = payload["mask_base64"]

        logger.info("[volc] image_inpaint")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: svc.image_inpaint(form))

        image_url = result.get("data", {}).get("image", "")
        if not image_url and result.get("data", {}).get("image_base64"):
            img_bytes = _base64_to_bytes(result["data"]["image_base64"])
            return {"image_bytes": img_bytes, "raw": result}

        img_bytes = _download_image(image_url) if image_url else b""
        return {"image_url": image_url, "image_bytes": img_bytes, "raw": result}

    async def _image_cut(self, ak: str, sk: str, image_bytes: bytes, payload: dict) -> dict:
        """图像智能裁剪 — image_cut"""
        import asyncio

        svc = _get_visual_service(ak, sk)
        b64 = _image_to_base64(image_bytes)

        width = payload.get("width", 512)
        height = payload.get("height", 512)
        cut_method = payload.get("cut_method", "ratio")  # "ratio" | "pixel"

        form = {
            "image_base64": b64,
            "width": width,
            "height": height,
            "cut_method": cut_method,
            "return_url": 1,
        }

        logger.info(f"[volc] image_cut {width}x{height} method={cut_method}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: svc.image_cut(form))

        image_url = result.get("data", {}).get("image", "")
        if not image_url and result.get("data", {}).get("image_base64"):
            img_bytes = _base64_to_bytes(result["data"]["image_base64"])
            return {"image_bytes": img_bytes, "raw": result}

        img_bytes = _download_image(image_url) if image_url else b""
        return {"image_url": image_url, "image_bytes": img_bytes, "raw": result}

    async def _image_outpaint(self, ak: str, sk: str, image_bytes: bytes, payload: dict) -> dict:
        """智能扩图 — image_outpaint"""
        import asyncio

        svc = _get_visual_service(ak, sk)
        b64 = _image_to_base64(image_bytes)

        form = {
            "image_base64": b64,
            "return_url": 1,
        }
        # 扩图比例，默认 1.5
        if payload.get("scale"):
            form["scale"] = payload["scale"]

        logger.info(f"[volc] image_outpaint scale={payload.get('scale', 1.5)}")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: svc.image_outpaint(form))

        image_url = result.get("data", {}).get("image", "")
        if not image_url and result.get("data", {}).get("image_base64"):
            img_bytes = _base64_to_bytes(result["data"]["image_base64"])
            return {"image_bytes": img_bytes, "raw": result}

        img_bytes = _download_image(image_url) if image_url else b""
        return {"image_url": image_url, "image_bytes": img_bytes, "raw": result}

    # ------------------------------------------------------------------
    # MediaKit Bearer Token API（集智瘦身 / 图像缩放）
    # ------------------------------------------------------------------

    async def _slim_image(self, image_bytes: bytes, payload: dict) -> dict:
        """集智瘦身 — POST /api/v1/tools-sync/slim-image"""
        import asyncio

        if not self.mediakit_api_key:
            raise ValueError("MediaKit API Key 未配置，无法调用集智瘦身")

        # 先上传图片获取 URL（或转为 base64 内联）
        b64 = _image_to_base64(image_bytes)
        data_uri = f"data:image/png;base64,{b64}"

        body = json.dumps({"image_url": data_uri}).encode("utf-8")
        url = f"{self._base_url}/tools-sync/slim-image"
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.mediakit_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        logger.info("[volc] slim_image")

        loop = asyncio.get_event_loop()
        result_json = await loop.run_in_executor(None, self._urlopen_json, req)

        if not result_json.get("success"):
            raise RuntimeError(f"集智瘦身失败: {result_json}")

        result_url = result_json.get("result", {}).get("image_url", "")
        img_bytes = _download_image(result_url) if result_url else b""
        return {"image_url": result_url, "image_bytes": img_bytes, "raw": result_json}

    async def _resize_image(self, image_bytes: bytes, payload: dict) -> dict:
        """图像缩放 — POST /api/v1/tools-sync/resize-image"""
        import asyncio

        if not self.mediakit_api_key:
            raise ValueError("MediaKit API Key 未配置，无法调用图像缩放")

        b64 = _image_to_base64(image_bytes)
        data_uri = f"data:image/png;base64,{b64}"

        body_data = {
            "image_url": data_uri,
            "resize_long": payload.get("resize_long", 0),
            "resize_short": payload.get("resize_short", 0),
            "resize_mode": payload.get("resize_mode", "contain"),
            "output_format": payload.get("output_format", "png"),
        }
        # 只允许一个维度为 0（等比缩放）
        if body_data["resize_long"] == 0 and body_data["resize_short"] == 0:
            body_data["resize_long"] = payload.get("width", 1024)

        body = json.dumps(body_data).encode("utf-8")
        url = f"{self._base_url}/tools-sync/resize-image"
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.mediakit_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        logger.info(f"[volc] resize_image {body_data}")

        loop = asyncio.get_event_loop()
        result_json = await loop.run_in_executor(None, self._urlopen_json, req)

        if not result_json.get("success"):
            raise RuntimeError(f"图像缩放失败: {result_json}")

        result_url = result_json.get("result", {}).get("image_url", "")
        img_bytes = _download_image(result_url) if result_url else b""
        return {"image_url": result_url, "image_bytes": img_bytes, "raw": result_json}

    def _urlopen_json(self, req: urllib.request.Request) -> dict:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
