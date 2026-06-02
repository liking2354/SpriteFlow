"""火山方舟 Seedream 5.0 Lite Provider

支持能力：
  - TEXT2IMG              文生图
  - IMG2IMG               图生图（单参考图）
  - MULTI_IMAGE_FUSION    多图融合（多参考图 → 单图）
  - SEQUENTIAL_IMAGES     多参考图生组图（一次出 N 张，可走流式）

API 文档：https://www.volcengine.com/docs/82379/1541523
统一端点：POST /images/generations
鉴权：Authorization: Bearer ${ARK_API_KEY}
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from typing import Any, AsyncIterator

import httpx
from PIL import Image

from .base import Capability, Credential, Provider


class SeedreamProvider(Provider):
    """火山方舟 Seedream 适配器"""

    name = "seedream"
    capabilities = {
        Capability.TEXT2IMG,
        Capability.IMG2IMG,
        Capability.MULTI_IMAGE_FUSION,
        Capability.SEQUENTIAL_IMAGES,
    }

    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
    DEFAULT_MODEL = "doubao-seedream-5-0-260128"

    def __init__(
        self,
        api_key: str = "",
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
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

        payload 字段（按需提供）：
          - prompt: str                              提示词（必填）
          - image: PIL.Image | str | list           参考图：PIL/URL/data-uri，list 用于多图
          - size: str = "2K"                         尺寸（"2K" / "1024x1024" / "adaptive"）
          - seed: int | None
          - max_images: int = 1                      SEQUENTIAL_IMAGES 时生效
          - stream: bool = False                     是否流式
          - web_search: bool = False                 是否启用联网搜索
          - watermark: bool = False
          - output_format: str = "png"
          - response_format: str = "url"
          - on_event: callable | None                流式事件回调

        Returns:
          {
            "images": [PIL.Image, ...],
            "raw_urls": [...],
            "sizes": [...],
            "usage": {...},
            "model": str,
          }
        """
        api_key = cred.api_key or self._api_key
        if not api_key:
            raise ValueError("Seedream Provider 缺少 ARK_API_KEY")

        body = self._build_body(cap, payload)

        if payload.get("stream") and cap == Capability.SEQUENTIAL_IMAGES:
            body["stream"] = True
            return await self._invoke_stream(body, api_key, payload.get("on_event"))

        return await self._invoke_non_stream(body, api_key)

    # ----------------------------- 请求体构造 ---------------------------

    def _build_body(self, cap: Capability, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = payload.get("prompt", "")
        if not prompt:
            raise ValueError("Seedream 调用必须提供 prompt")

        body: dict[str, Any] = {
            "model": payload.get("model") or self._model,
            "prompt": prompt,
            "size": payload.get("size", "2K"),
            "output_format": payload.get("output_format", "png"),
            "response_format": payload.get("response_format", "url"),
            "watermark": bool(payload.get("watermark", False)),
        }

        if (seed := payload.get("seed")) is not None:
            body["seed"] = int(seed)
        if (gs := payload.get("guidance_scale")) is not None:
            body["guidance_scale"] = float(gs)

        # ---- 参考图 ----
        if cap == Capability.IMG2IMG:
            ref = payload.get("image")
            if ref is None:
                raise ValueError("IMG2IMG 需要 image 输入")
            body["image"] = self._encode_image(ref)
            body["sequential_image_generation"] = "disabled"

        elif cap == Capability.MULTI_IMAGE_FUSION:
            refs = payload.get("image")
            if not isinstance(refs, list) or len(refs) < 2:
                raise ValueError("MULTI_IMAGE_FUSION 需要至少 2 张参考图（list[PIL/URL]）")
            body["image"] = [self._encode_image(r) for r in refs]
            body["sequential_image_generation"] = "disabled"

        elif cap == Capability.SEQUENTIAL_IMAGES:
            refs = payload.get("image")
            if refs is not None:
                if isinstance(refs, list):
                    body["image"] = [self._encode_image(r) for r in refs]
                else:
                    body["image"] = self._encode_image(refs)
            body["sequential_image_generation"] = "auto"
            body["sequential_image_generation_options"] = {
                "max_images": int(payload.get("max_images", 4)),
            }

        # ---- 联网搜索 ----
        if payload.get("web_search"):
            body["tools"] = [{"type": "web_search"}]

        return body

    # ----------------------------- 非流式调用 ---------------------------

    async def _invoke_non_stream(
        self, body: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        url = f"{self._base_url}/images/generations"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                headers=self._auth_headers(api_key),
                json=body,
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Seedream API 错误 {resp.status_code}: {resp.text}"
                )
            data = resp.json()

        items = data.get("data", []) or []
        urls = [it.get("url") for it in items if it.get("url")]
        b64s = [it.get("b64_json") for it in items if it.get("b64_json")]
        sizes = [it.get("size") for it in items]

        images = await self._materialize(urls, b64s)

        return {
            "images": images,
            "image": images[0] if images else None,  # 兼容单图返回
            "raw_urls": urls,
            "sizes": sizes,
            "usage": data.get("usage", {}),
            "model": data.get("model"),
        }

    # ----------------------------- 流式调用 -----------------------------

    async def _invoke_stream(
        self,
        body: dict[str, Any],
        api_key: str,
        on_event: Any | None,
    ) -> dict[str, Any]:
        """SSE 流式：逐张拿 partial_succeeded，最后 completed"""
        url = f"{self._base_url}/images/generations"
        urls: list[str] = []
        sizes: list[str] = []
        usage: dict[str, Any] = {}
        model: str | None = None

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                url,
                headers={**self._auth_headers(api_key), "Accept": "text/event-stream"},
                json=body,
            ) as resp:
                if resp.status_code >= 400:
                    text = await resp.aread()
                    raise RuntimeError(
                        f"Seedream 流式错误 {resp.status_code}: {text.decode(errors='ignore')}"
                    )

                async for evt in self._iter_sse(resp):
                    etype = evt.get("type", "")
                    if etype == "image_generation.partial_succeeded":
                        u = evt.get("url")
                        if u:
                            urls.append(u)
                            sizes.append(evt.get("size", ""))
                        if on_event:
                            await _maybe_call(on_event, evt)
                    elif etype == "image_generation.partial_failed":
                        if on_event:
                            await _maybe_call(on_event, evt)
                    elif etype == "image_generation.completed":
                        usage = evt.get("usage", {}) or {}
                        model = evt.get("model")
                        if on_event:
                            await _maybe_call(on_event, evt)

        images = await self._materialize(urls, [])

        return {
            "images": images,
            "image": images[0] if images else None,
            "raw_urls": urls,
            "sizes": sizes,
            "usage": usage,
            "model": model,
        }

    @staticmethod
    async def _iter_sse(resp: httpx.Response) -> AsyncIterator[dict[str, Any]]:
        """解析 SSE 流，按 'event: x\\ndata: {...}\\n\\n' 拆分"""
        buf = ""
        async for chunk in resp.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                raw, buf = buf.split("\n\n", 1)
                data_lines = [
                    line[5:].lstrip()
                    for line in raw.splitlines()
                    if line.startswith("data:")
                ]
                if not data_lines:
                    continue
                payload = "\n".join(data_lines).strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    # ----------------------------- 工具方法 -----------------------------

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _encode_image(ref: Any) -> str:
        """把参考图统一编码为 URL 或 data:image/png;base64,...

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
            mime = "image/png"
            return f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        if isinstance(ref, bytes):
            return f"data:image/png;base64,{base64.b64encode(ref).decode()}"
        if isinstance(ref, Image.Image):
            buf = io.BytesIO()
            ref.convert("RGBA").save(buf, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
        raise TypeError(f"不支持的参考图类型: {type(ref).__name__}")

    @staticmethod
    async def _materialize(
        urls: list[str], b64s: list[str]
    ) -> list[Image.Image]:
        """把 URL/base64 → PIL.Image 列表（并发下载）"""
        images: list[Image.Image] = []

        for b in b64s:
            raw = base64.b64decode(b)
            images.append(Image.open(io.BytesIO(raw)).convert("RGBA"))

        if urls:
            async with httpx.AsyncClient(timeout=120.0) as client:
                results = await asyncio.gather(
                    *(client.get(u) for u in urls), return_exceptions=True
                )
                for r in results:
                    if isinstance(r, Exception):
                        raise RuntimeError(f"下载 Seedream 输出图片失败: {r}")
                    r.raise_for_status()
                    images.append(Image.open(io.BytesIO(r.content)).convert("RGBA"))

        return images


async def _maybe_call(fn: Any, *args: Any) -> None:
    """on_event 回调容错：支持同步/异步函数"""
    try:
        result = fn(*args)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        pass
