"""OpenRouter Provider — 统一多模型图片生成入口

OpenRouter 通过 OpenAI-compatible API 对接多种图像生成模型：
  - openai/gpt-image-1          ChatGPT Image2（角色母版）
  - google/gemini-2.5-flash-image Gemini 2.5 Flash Image
  - bytedance/doubao-seedream-4.5   Seedream 4.5（四视图）
  - 以及更多模型 ...

API 文档：https://openrouter.ai/docs
统一端点：POST https://openrouter.ai/api/v1/chat/completions
鉴权：Authorization: Bearer ${OPENROUTER_API_KEY}

请求格式（text2img）：
  {
    "model": "openai/gpt-image-1",
    "messages": [{"role": "user", "content": "生成一个战士角色"}],
    "modalities": ["image", "text"]
  }

请求格式（img2img）：
  {
    "model": "...",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "text", "text": "基于此参考图生成..."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
      ]
    }],
    "modalities": ["image", "text"]
  }

返回格式（与 SeedreamProvider 一致）：
  {
    "images": [PIL.Image, ...],
    "image": PIL.Image | None,
    "usage": {...},
    "model": str,
  }
"""

from __future__ import annotations

import base64
import io
import json
import logging
from typing import Any

import httpx
from PIL import Image

from .base import Capability, Credential, Provider

logger = logging.getLogger("spriteflow.openrouter")


class OpenRouterProvider(Provider):
    """OpenRouter 多模型适配器"""

    name = "openrouter"
    capabilities = {
        Capability.TEXT2IMG,
        Capability.IMG2IMG,
        Capability.CHARACTER_MASTER,
        Capability.FOUR_VIEW,
    }

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "openai/gpt-image-1"

    def __init__(
        self,
        api_key: str = "",
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._model = model or self.DEFAULT_MODEL
        self._timeout = timeout

    # ----------------------------- 公共入口 -----------------------------

    async def invoke(
        self,
        cap: Capability,
        payload: dict[str, Any],
        cred: Credential,
    ) -> dict[str, Any]:
        """统一调用入口

        payload 字段：
          - prompt: str                              提示词（必填）
          - image: PIL.Image | str                   参考图（img2img 时必填）
          - size: str = "1024x1024"                  目标尺寸（建议值，非所有模型支持）
          - model: str | None                        覆盖默认模型
          - max_images: int = 1                      生成数量（n 参数）
          - temperature: float = 1.0
          - top_p: float = 1.0

        Returns:
          {
            "images": [PIL.Image, ...],
            "image": PIL.Image | None,
            "usage": {...},
            "model": str,
          }
        """
        api_key = cred.api_key or self._api_key
        if not api_key:
            raise ValueError("OpenRouter Provider 缺少 OPENROUTER_API_KEY")

        body = self._build_body(cap, payload)
        return await self._invoke(body, api_key)

    # ----------------------------- 请求体构造 ---------------------------

    # 场景 → 推荐默认模型
    _SCENE_MODEL: dict[Capability, str] = {
        Capability.CHARACTER_MASTER: "openai/gpt-image-1",
        Capability.FOUR_VIEW: "bytedance/doubao-seedream-4.5",
    }

    def _build_body(self, cap: Capability, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = payload.get("prompt", "")
        if not prompt:
            raise ValueError("OpenRouter 调用必须提供 prompt")

        # 模型优先级：payload.model > 场景默认 > provider 默认
        model = (
            payload.get("model")
            or self._SCENE_MODEL.get(cap)
            or self._model
        )
        n = int(payload.get("max_images", 1))

        # 构造 messages（character_master / four_view 内部走 text2img 逻辑）
        is_img2img = cap in (Capability.IMG2IMG,)
        if is_img2img:
            ref = payload.get("image")
            if ref is None:
                raise ValueError("IMG2IMG 需要 image 输入")
            encoded_ref = self._encode_image(ref)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": encoded_ref},
                        },
                    ],
                }
            ]
        else:
            messages = [{"role": "user", "content": prompt}]

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "modalities": ["image", "text"],
            "n": n,
        }

        if (temperature := payload.get("temperature")) is not None:
            body["temperature"] = float(temperature)
        if (top_p := payload.get("top_p")) is not None:
            body["top_p"] = float(top_p)

        # size 通过 extra_body 传递（部分模型支持）
        if (size := payload.get("size")):
            body.setdefault("extra_body", {})["size"] = size

        return body

    # ----------------------------- 调用逻辑 ---------------------------

    async def _invoke(
        self, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        url = f"{self._base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                headers=self._auth_headers(api_key),
                json=body,
            )
            if resp.status_code >= 400:
                raise self._parse_error(resp)
            data = resp.json()

        # 提取图片
        images = self._extract_images(data)
        usage = data.get("usage", {})
        model = data.get("model")

        return {
            "images": images,
            "image": images[0] if images else None,
            "usage": usage,
            "model": model,
        }

    def _extract_images(self, data: dict[str, Any]) -> list[Image.Image]:
        """从 OpenRouter 响应中提取图片

        OpenRouter 返回格式（类似 OpenAI chat completions）：
          choices[0].message.content:
            - 字符串（纯文本，无图片）
            - list[...]  每项可能是 {"type": "image_url", "image_url": {"url": "..."}}
            或 {"type": "text", "text": "..."}

        图片 URL 可能是：
          - data:image/png;base64,...   (base64 inline)
          - https://...                   (外部 URL)
        """
        images: list[Image.Image] = []

        choices = data.get("choices", [])
        for choice in choices:
            msg = choice.get("message", {})
            content = msg.get("content")

            if isinstance(content, str):
                # 纯文本，忽略
                continue

            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        img_url_data = part.get("image_url", {})
                        url = img_url_data.get("url", "")
                        if url:
                            img = self._load_image_from_url(url)
                            if img:
                                images.append(img)

        return images

    @staticmethod
    def _load_image_from_url(url: str) -> Image.Image | None:
        """从 URL（base64 data URI 或 http URL）加载图片"""
        try:
            if url.startswith("data:"):
                # data:image/png;base64,...
                header, data = url.split(",", 1)
                raw = base64.b64decode(data)
                return Image.open(io.BytesIO(raw)).convert("RGBA")
            elif url.startswith(("http://", "https://")):
                # 需要异步下载，统一用同步 httpx
                import httpx as _httpx
                resp = _httpx.get(url, timeout=30, follow_redirects=True)
                resp.raise_for_status()
                return Image.open(io.BytesIO(resp.content)).convert("RGBA")
            else:
                logger.warning("[openrouter] 不支持的图片 URL 格式: %s", url[:80])
                return None
        except Exception as e:
            logger.warning("[openrouter] 加载图片失败: %s: %r", type(e).__name__, e)
            return None

    # ----------------------------- 工具方法 -----------------------------

    @staticmethod
    def _parse_error(resp: httpx.Response) -> RuntimeError:
        """解析 API 错误响应"""
        try:
            data = resp.json()
            err = data.get("error", {})
            code = err.get("code", "")
            msg = err.get("message", "")
        except Exception:
            code = ""
            msg = resp.text
        return RuntimeError(
            f"OpenRouter API 错误 {resp.status_code} ({code}): {msg or resp.text}"
        )

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://spriteflow.app",
            "X-Title": "SpriteFlow",
        }

    @staticmethod
    def _encode_image(ref: Any) -> str:
        """把参考图统一编码为 data:image/png;base64,...

        - http(s):// URL 直接透传
        - data:image/...;base64,... 直接透传
        - PIL.Image  → base64 data URI
        - bytes      → base64 data URI
        """
        if isinstance(ref, str):
            if ref.startswith(("http://", "https://", "data:")):
                return ref
            # 视为本地路径
            with open(ref, "rb") as f:
                raw = f.read()
            return f"data:image/png;base64,{base64.b64encode(raw).decode()}"
        if isinstance(ref, bytes):
            return f"data:image/png;base64,{base64.b64encode(ref).decode()}"
        if isinstance(ref, Image.Image):
            buf = io.BytesIO()
            ref.convert("RGBA").save(buf, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
        raise TypeError(f"不支持的参考图类型: {type(ref).__name__}")
