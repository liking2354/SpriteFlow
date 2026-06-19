"""
Seedance 1.0 Pro Fast 组件

基于火山方舟 Seedance API 的视频生成组件，
支持首帧参考图，独立参数配置（不同于默认 Seedance 模型版本）。

API 文档:
  https://www.volcengine.com/docs/82379/1541595 (SDK)
  https://www.volcengine.com/docs/82379/1520757 (创建任务)
  https://www.volcengine.com/docs/82379/1521309 (查询任务)

依赖: httpx（已有，SeedanceProvider 已使用）
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from ..base import Component, ComponentMeta

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "doubao-seedance-1-0-pro-fast-251015"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# 任务终态
SETTLED = {"succeeded", "failed", "cancelled", "expired"}

ASPECT_RATIOS = [
    {"value": "21:9", "label": "21:9"},
    {"value": "16:9", "label": "16:9"},
    {"value": "4:3", "label": "4:3"},
    {"value": "1:1", "label": "1:1"},
    {"value": "3:4", "label": "3:4"},
    {"value": "9:16", "label": "9:16"},
]

RESOLUTIONS = [
    {"value": "480p", "label": "480p"},
    {"value": "720p", "label": "720p"},
    {"value": "1080p", "label": "1080p"},
]

DURATION_MODES = [
    {"value": "seconds", "label": "按秒数"},
    {"value": "frames", "label": "按帧数"},
]

FRIENDLY_ERRORS = {
    "InputImageSensitiveContentDetected": (
        "输入图片被审核判定为含敏感信息。Seedance 不支持真人脸参考图，"
        "且对暴露/敏感内容审核较严，请改用 AI 生成的角色/物体/场景图。"
    ),
    "InputTextSensitiveContentDetected": "提示词被审核判定为含敏感信息，请避免涉政/暴力/色情等内容。",
    "InvalidEndpointOrModel": (
        "模型 ID 不存在或未开通。请确认：\n"
        "1. 模型 ID 是否正确（Seedance 1.0 Pro Fast = doubao-seedance-1-0-pro-fast-251015）\n"
        "2. 是否已在火山方舟控制台 → 在线推理 开通该模型\n"
        "3. 如使用推理接入点，请将凭据中的「模型 ID」替换为 Endpoint ID（格式: ep-xxxxxxxxxxxx）"
    ),
    "ModelNotOpen": "当前模型未开通。请到火山方舟控制台开通对应模型。",
    "InvalidParameter": "参数错误：请检查比例/分辨率/时长是否在模型支持范围内。",
    "RateLimitExceeded": "触发限流，请稍后重试。",
    "InsufficientQuota": "账号额度不足，请前往控制台充值或调整。",
}


class SeedanceProFastComponent(Component):
    """Seedance 1.0 Pro Fast 视频生成组件"""

    @property
    def meta(self) -> ComponentMeta:
        return ComponentMeta(
            component_id="seedance-v1-pro-fast",
            display_name="Seedance 1.0 Pro Fast",
            category="custom",
            subcategory="video",
            description="火山方舟 Seedance 1.0 Pro Fast 视频生成（支持首帧参考图、多种比例/分辨率/时长模式）",
            version="1.0.0",
            icon="🎬",
            output_type="video_url",
            # 凭据配置（用户可在组件管理中填写）
            credential_schema={
                "type": "object",
                "properties": {
                    "ark_api_key": {
                        "type": "string",
                        "title": "ARK API Key",
                        "description": "火山方舟 API Key",
                        "format": "password",
                    },
                    "ark_base_url": {
                        "type": "string",
                        "title": "ARK Base URL",
                        "description": "火山方舟 API 地址",
                        "default": DEFAULT_BASE_URL,
                    },
                    "seedance_model": {
                        "type": "string",
                        "title": "模型 ID",
                        "description": "Seedance 模型 ID",
                        "default": DEFAULT_MODEL,
                    },
                },
                "required": ["ark_api_key", "ark_base_url", "seedance_model"],
            },
            # 每次执行的输入参数 schema
            input_schema={
                "prompt": {
                    "type": "string",
                    "title": "提示词",
                    "description": "描述要生成的视频内容",
                },
                "image_url": {
                    "type": "string",
                    "title": "首帧参考图",
                    "description": "可选首帧参考图 URL（图生视频）",
                    "format": "uri",
                },
                "aspect_ratio": {
                    "type": "string",
                    "title": "视频比例",
                    "enum": [r["value"] for r in ASPECT_RATIOS],
                    "enumNames": [r["label"] for r in ASPECT_RATIOS],
                    "default": "16:9",
                },
                "resolution": {
                    "type": "string",
                    "title": "分辨率",
                    "enum": [r["value"] for r in RESOLUTIONS],
                    "enumNames": [r["label"] for r in RESOLUTIONS],
                    "default": "480p",
                },
                "duration_mode": {
                    "type": "string",
                    "title": "时长模式",
                    "enum": ["seconds", "frames"],
                    "enumNames": ["按秒数", "按帧数"],
                    "default": "seconds",
                    "defaultLabel": "按秒数",
                },
                "duration_seconds": {
                    "type": "integer",
                    "title": "视频时长（秒）",
                    "description": "按秒数生成，最多12秒",
                    "default": 2,
                    "minimum": 1,
                    "maximum": 12,
                    "step": 1,
                },
                "duration_frames": {
                    "type": "integer",
                    "title": "视频帧数",
                    "description": "按帧数生成，最小29帧，最大289帧",
                    "default": 29,
                    "minimum": 29,
                    "maximum": 289,
                    "step": 1,
                },
                "num_outputs": {
                    "type": "integer",
                    "title": "生成数量",
                    "description": "单次任务生成视频数量，最多8条",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 8,
                    "step": 1,
                },
                "seed": {
                    "type": "integer",
                    "title": "种子值",
                    "description": "随机种子（-1 为随机）",
                    "default": -1,
                    "minimum": -1,
                    "step": 1,
                },
                "generation_timeout": {
                    "type": "integer",
                    "title": "生成超时时间（秒）",
                    "description": "等待生成完成的最大时间",
                    "default": 600,
                    "minimum": 60,
                    "maximum": 3600,
                },
                "fixed_camera": {
                    "type": "boolean",
                    "title": "固定镜头",
                    "description": "是否启用固定镜头",
                    "default": False,
                },
            },
            input_required=["prompt"],
        )

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    async def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        mode = params.get("duration_mode", "seconds")
        if mode == "seconds":
            dur = params.get("duration_seconds", 5)
            if not 1 <= dur <= 12:
                errors.append("按秒数模式下，duration_seconds 需要在 1~12 之间")
        elif mode == "frames":
            frames = params.get("duration_frames", 121)
            if not 29 <= frames <= 289:
                errors.append("按帧数模式下，duration_frames 需要在 29~289 之间")
        return errors

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def execute(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行 Seedance 视频生成"""
        # 1. 解析凭据（优先传参，其次 .env）
        from spriteflow.config import settings as env_settings

        creds = credentials or {}
        api_key = creds.get("ark_api_key") or env_settings.ark_api_key
        base_url = (
            creds.get("ark_base_url")
            or env_settings.ark_base_url
            or DEFAULT_BASE_URL
        )
        model = creds.get("seedance_model") or DEFAULT_MODEL

        if not api_key:
            raise ValueError("ARK_API_KEY 未配置，请在组件参数或 .env 中设置")

        base_url = base_url.rstrip("/")

        # 2. 构建请求体
        prompt = inputs.get("prompt", "")
        image_url = inputs.get("image_url") or inputs.get("image") or ""

        # 诊断日志：输出实际收到的参数
        logger.info(
            "[SeedanceProFast] inputs keys=%s, params keys=%s, has_image_url=%s, image_url_sample=%s",
            list(inputs.keys()),
            list(params.keys()),
            bool(image_url),
            image_url[:120] if image_url else "NONE",
        )

        # Ark Seedance API: content 是数组，每项含 type 字段
        # 参考文档: https://www.volcengine.com/docs/82379/1520757
        content: list[dict[str, Any]] = []
        if prompt:
            content.append({"type": "text", "text": prompt})
        if image_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url},
                "role": "first_frame",
            })

        mode = params.get("duration_mode", "seconds")
        body: dict[str, Any] = {
            "model": model,
            "content": content,
            "ratio": params.get("aspect_ratio", "16:9"),
            "resolution": params.get("resolution", "720p"),
            "seed": params.get("seed", -1),
            "camera_fixed": params.get("fixed_camera", False),
        }

        logger.info(
            "[SeedanceProFast] API body: model=%s, content_items=%d, has_image=%s",
            model,
            len(content),
            bool(image_url),
        )

        if params.get("num_outputs", 1) > 1:
            body["num_outputs"] = params["num_outputs"]

        if mode == "frames":
            body["frames"] = params.get("duration_frames", 29)
        else:
            body["duration"] = params.get("duration_seconds", 5)

        timeout = params.get("generation_timeout", 600)

        logger.info(
            "[SeedanceProFast] FULL body: %s",
            json.dumps(body, ensure_ascii=False, default=str),
        )

        logger.info(
            "[SeedanceProFast] creating task: model=%s ratio=%s resolution=%s duration_mode=%s",
            model,
            body.get("ratio"),
            body.get("resolution"),
            mode,
        )

        # 3. 创建任务
        task_response = await self._create_task(body, api_key, base_url)
        task_id = task_response.get("id") or task_response.get("task_id")
        if not task_id:
            raise RuntimeError(f"创建任务失败，未返回 task_id: {task_response}")

        logger.info("[SeedanceProFast] task created: %s", task_id)

        # 4. 轮询等待完成
        try:
            result = await self._poll_task(task_id, api_key, base_url, timeout)
        except asyncio.TimeoutError:
            raise RuntimeError(f"视频生成超时 ({timeout}s)，task_id={task_id}")

        status = result.get("status", "unknown")
        if status == "succeeded":
            video_url = self._extract_video_url(result)
            if not video_url:
                raise RuntimeError(f"生成成功但未获取到视频 URL，task_id={task_id}")

            logger.info("[SeedanceProFast] succeeded: %s", video_url[:120])

            # 下载视频并存入素材库（视频 URL 24h 有效，必须立即落库）
            asset_id = None
            try:
                from spriteflow.api.deps import get_db, get_storage
                from spriteflow.providers.seedance import SeedanceProvider
                from spriteflow.asset_hub.ingest import IngestPipeline

                video_data = await SeedanceProvider.download_video(video_url)
                db = get_db()
                storage = get_storage()
                ingest = IngestPipeline(storage, db)
                asset = await ingest.ingest_video(
                    video_data,
                    ext="mp4",
                    content_type="video/mp4",
                    tags=["video", "seedance-pro-fast", "generated"],
                    provenance={
                        "component": "seedance-v1-pro-fast",
                        "task_id": task_id,
                        "model": model,
                        "prompt": prompt,
                    },
                )
                asset_id = asset.id
                logger.info("[SeedanceProFast] saved to asset library: %s", asset_id)
            except Exception as save_err:
                logger.warning(
                    "[SeedanceProFast] save to asset library failed (video_url still valid): %s",
                    save_err,
                )

            outputs: list[dict[str, str]] = [
                {"type": "video_url", "value": video_url},
            ]
            if asset_id:
                outputs.append({"type": "asset_id", "value": asset_id})
            return {"outputs": outputs}
        else:
            error_msg = result.get("error", {}).get("message", str(result))
            friendly = FRIENDLY_ERRORS.get(
                result.get("error", {}).get("code", ""), ""
            )
            raise RuntimeError(
                friendly or f"视频生成失败 (status={status}): {error_msg}"
            )

    # ------------------------------------------------------------------
    # API 调用
    # ------------------------------------------------------------------

    async def _create_task(
        self, body: dict[str, Any], api_key: str, base_url: str
    ) -> dict[str, Any]:
        url = f"{base_url}/contents/generations/tasks"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as cli:
            r = await cli.post(url, headers=headers, json=body)
            if not r.is_success:
                self._raise_api_error(r)
            return r.json()

    async def _poll_task(
        self,
        task_id: str,
        api_key: str,
        base_url: str,
        timeout: float,
        poll_interval: float = 5.0,
    ) -> dict[str, Any]:
        url = f"{base_url}/contents/generations/tasks/{task_id}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        deadline = asyncio.get_event_loop().time() + timeout

        async with httpx.AsyncClient(timeout=30.0) as cli:
            while True:
                r = await cli.get(url, headers=headers)
                if not r.is_success:
                    self._raise_api_error(r)
                result = r.json()
                status = result.get("status", "unknown")
                logger.debug(
                    "[SeedanceProFast] poll %s: status=%s", task_id, status
                )

                if status in SETTLED:
                    return result

                if asyncio.get_event_loop().time() > deadline:
                    raise asyncio.TimeoutError(
                        f"任务 {task_id} 在 {timeout}s 内未完成"
                    )

                await asyncio.sleep(poll_interval)

    @staticmethod
    def _extract_video_url(result: dict[str, Any]) -> str | None:
        """从成功结果中提取视频 URL

        火山方舟查询任务接口返回格式：
          { "status": "succeeded", "content": { "video_url": "https://..." }, ... }

        content 是一个对象（dict），不是数组。
        """
        content_obj = result.get("content") or {}
        video_url = content_obj.get("video_url")
        if isinstance(video_url, str) and video_url.strip():
            return video_url.strip()
        # 兜底：部分代理层可能把 video_url 放在顶层
        top_url = result.get("video_url")
        if isinstance(top_url, str) and top_url.strip():
            return top_url.strip()
        # 调试日志：打印原始 content 结构帮助排查
        logger.warning(
            "[SeedanceProFast] unexpected response format, content type=%s keys=%s",
            type(content_obj).__name__,
            list(content_obj.keys()) if isinstance(content_obj, dict) else "N/A",
        )
        return None

    @staticmethod
    def _raise_api_error(r: httpx.Response) -> None:
        try:
            payload = r.json()
        except Exception:
            payload = {"raw": r.text}
        err = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(err, dict):
            code = str(err.get("code", r.status_code))
            msg = err.get("message", r.text)
            friendly = FRIENDLY_ERRORS.get(code)
            if friendly:
                raise RuntimeError(f"{friendly}\n（原始：{code}: {msg}）")
            raise RuntimeError(f"Seedance API {r.status_code} {code}: {msg}")
        raise RuntimeError(f"Seedance API {r.status_code}: {payload}")
