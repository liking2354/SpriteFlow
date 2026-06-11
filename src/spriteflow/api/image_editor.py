"""
即梦AI 交互编辑 Inpainting API

POST /api/image-editor/inpaint  → 提交 CVSync2Async 任务
GET  /api/image-editor/inpaint/{task_id}  → 轮询结果

API 文档: https://www.volcengine.com/docs/85621/1976207
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..config import settings

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# 即梦AI 配置
# ---------------------------------------------------------------------------
VISUAL_HOST = "visual.volcengineapi.com"
VISUAL_SERVICE = "cv"
VISUAL_REGION = "cn-north-1"
VISUAL_API_VERSION = "2022-08-31"

# 内存任务存储 (生产应改用 DB/Redis)
_tasks: dict[str, dict] = {}

# API 错误码 → 中文提示 映射
_ERROR_MAP: dict[int, str] = {
    50411: "输入图片未通过内容审核，请更换图片",
    50511: "AI 生成结果未通过内容审核，请重试",
    50412: "提示词含敏感内容，请修改后重试",
    50512: "提示词含敏感内容，请修改后重试",
    50413: "提示词含敏感词或版权词，请修改后重试",
    50518: "输入图片含版权内容，请更换图片",
    50519: "AI 生成结果含版权内容，请重试",
    50520: "内容审核服务异常，请稍后重试",
    50521: "版权检测服务异常，请稍后重试",
    50522: "版权图检测服务异常，请稍后重试",
    50429: "请求过于频繁（QPS 超限），请稍后重试",
    50430: "并发请求过多，请稍后重试",
    50500: "AI 服务内部错误，请稍后重试",
    50501: "AI 算法服务异常，请稍后重试",
}


def _friendly_error(code: int, default_msg: str) -> str:
    """将 API 错误码转为中文提示"""
    return _ERROR_MAP.get(code, f"API 错误[{code}]: {default_msg}")


# ---------------------------------------------------------------------------
# Volcengine V4 签名 (HMAC-SHA256)
# ---------------------------------------------------------------------------

def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign_request(
    method: str,
    path: str,
    query: str,
    headers: dict[str, str],
    body: bytes,
    ak: str,
    sk: str,
    service: str = VISUAL_SERVICE,
    region: str = VISUAL_REGION,
) -> str:
    """生成 Volcengine V4 Authorization header"""
    t = datetime.now(timezone.utc)
    timestamp = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    # 设置签名必需的 header
    headers["Host"] = VISUAL_HOST
    headers["X-Date"] = timestamp
    headers["Content-Type"] = "application/json"

    # CanonicalRequest
    canonical_uri = path
    canonical_querystring = query
    signed_headers = "content-type;host;x-date"
    payload_hash = _sha256_hex(body)

    canonical_request = f"{method}\n{canonical_uri}\n{canonical_querystring}\ncontent-type:{headers['Content-Type']}\nhost:{headers['Host']}\nx-date:{headers['X-Date']}\n\n{signed_headers}\n{payload_hash}"

    # StringToSign
    algorithm = "HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/request"
    string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{_sha256_hex(canonical_request.encode('utf-8'))}"

    # Signing Key
    k_date = _hmac_sha256(sk.encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    signing_key = _hmac_sha256(k_service, "request")

    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return (
        f"{algorithm} Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def _call_visual_service(action: str, params: dict, ak: str, sk: str) -> dict:
    """调用火山引擎视觉智能服务 CVSync2Async API"""
    body = json.dumps(params).encode("utf-8")
    headers: dict[str, str] = {}

    path = "/"
    query = f"Action={action}&Version={VISUAL_API_VERSION}"
    auth = _sign_request("POST", path, query, headers, body, ak, sk)

    headers["Authorization"] = auth

    url = f"https://{VISUAL_HOST}{path}?{query}"

    # 记录请求概要（不含敏感数据）
    if action == "CVSync2AsyncSubmitTask":
        log_params = {k: v for k, v in params.items() if k not in ("binary_data_base64",)}
        log_params["binary_data_base64_count"] = len(params.get("binary_data_base64", []))
        if params.get("binary_data_base64"):
            for i, b64 in enumerate(params["binary_data_base64"]):
                log_params[f"b64[{i}]_len"] = len(b64) if isinstance(b64, str) else "?"
        logger.info(f"[call] {action} params={json.dumps(log_params, ensure_ascii=False)}")
    else:
        logger.info(f"[call] {action} task_id={params.get('task_id')}")

    # 输出完整请求体（截断 base64 字段）
    debug_body = json.loads(body.decode("utf-8"))
    if "binary_data_base64" in debug_body:
        debug_body["binary_data_base64"] = [f"<b64 len={len(b)} first10={b[:10]}...>" for b in debug_body["binary_data_base64"]]
    logger.info(f"[call] {action} FULL BODY: {json.dumps(debug_body, ensure_ascii=False)}")

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            # 截断长字段
            if action == "CVSync2AsyncGetResult":
                log_result = json.loads(json.dumps(result))
                if log_result.get("data", {}).get("binary_data_base64"):
                    log_result["data"]["binary_data_base64"] = [f"<base64 len={len(log_result['data']['binary_data_base64'][0])}>"]
                logger.info(f"[call] {action} response={json.dumps(log_result, ensure_ascii=False)[:800]}")
            else:
                logger.info(f"[call] {action} response code={result.get('code')} task_id={result.get('data', {}).get('task_id', '?')}")
            return result
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        logger.error(f"[call] {action} HTTP {e.code}: {err_body[:500]}")
        # 尝试解析错误码
        detail = f"即梦AI API 错误 {e.code}: {err_body[:200]}"
        try:
            err_json = json.loads(err_body)
            err_code = err_json.get("code", 0)
            err_msg = err_json.get("message", "")
            if err_code:
                detail = _friendly_error(err_code, err_msg)
        except (json.JSONDecodeError, ValueError):
            pass
        raise HTTPException(status_code=502, detail=detail)


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class InpaintSubmitResponse(BaseModel):
    task_id: str


class InpaintPollResponse(BaseModel):
    status: str  # "running" | "succeeded" | "failed"
    image_base64: str = ""
    image_url: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/image-editor/inpaint", response_model=InpaintSubmitResponse)
async def inpaint_submit(
    file: UploadFile = File(...),
    mask_file: UploadFile = File(...),
    prompt: str = Form(default=""),
):
    """提交交互编辑任务

    - file: 原图
    - mask_file: mask图（同尺寸，白色=编辑区，黑色=保留区）
    - prompt: 编辑提示词（"删除"=擦除模式）
    """
    ak = settings.volc_access_key_id
    sk = settings.volc_secret_access_key
    if not ak or not sk:
        raise HTTPException(status_code=400, detail="火山引擎 AK/SK 未配置")

    # 读取图片
    image_bytes = await file.read()
    mask_bytes = await mask_file.read()

    # mask 转灰度：如果前端导出的是 RGBA，转为单通道 L 灰度图
    try:
        import io
        from PIL import Image
        mask_img = Image.open(io.BytesIO(mask_bytes))
        if mask_img.mode not in ("L", "LA"):
            logger.info(f"[inpaint submit] 转换 mask 从 {mask_img.mode} → L")
            mask_img = mask_img.convert("L")
            mask_buf = io.BytesIO()
            mask_img.save(mask_buf, format="PNG")
            mask_bytes = mask_buf.getvalue()
    except Exception as e:
        logger.warning(f"[inpaint submit] mask 转换失败，使用原始数据: {e}")

    # 解码图片获取尺寸并压缩 (API 限制: ≤4.7MB, ≤4096px, 建议 JPEG)
    MAX_SIZE = 4096
    MAX_BYTES = 4.7 * 1024 * 1024

    try:
        orig_img = Image.open(io.BytesIO(image_bytes))
        mask_img2 = Image.open(io.BytesIO(mask_bytes))
        logger.info(f"[inpaint submit] orig_dim={orig_img.size} mask_dim={mask_img2.size} mask_mode={mask_img2.mode}")

        # 如果图片 > 4.7MB 或 > 4096px，压缩为 JPEG
        needs_compress = (
            len(image_bytes) > MAX_BYTES
            or orig_img.width > MAX_SIZE
            or orig_img.height > MAX_SIZE
        )
        if needs_compress:
            if orig_img.width > MAX_SIZE or orig_img.height > MAX_SIZE:
                orig_img.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)
                mask_img2 = mask_img2.resize(orig_img.size, Image.NEAREST)
                logger.info(f"[inpaint submit] 缩放至 {orig_img.size}")

            image_buf = io.BytesIO()
            orig_img.convert("RGB").save(image_buf, format="JPEG", quality=85)
            image_bytes = image_buf.getvalue()
            logger.info(f"[inpaint submit] 压缩原图 {len(image_bytes)}B")

            # mask 也转 JPEG（灰度图，高质）
            mask_buf = io.BytesIO()
            mask_img2.save(mask_buf, format="JPEG", quality=95)
            mask_bytes = mask_buf.getvalue()
    except Exception as e:
        logger.warning(f"[inpaint submit] 图片处理失败: {e}")

    # 转为 base64
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    mask_b64 = base64.b64encode(mask_bytes).decode("utf-8")

    logger.info(f"[inpaint submit] prompt={prompt!r}, orig_size={len(image_bytes)}B, mask_size={len(mask_bytes)}B")
    logger.info(f"[inpaint submit] orig_b64_len={len(image_b64)}, mask_b64_len={len(mask_b64)}")

    # 构建请求
    params = {
        "req_key": "jimeng_image2image_dream_inpaint",
        "binary_data_base64": [image_b64, mask_b64],
        "prompt": prompt or "删除",
    }

    result = _call_visual_service("CVSync2AsyncSubmitTask", params, ak, sk)

    resp_data = result.get("data", {})
    task_id = resp_data.get("task_id", "")
    if not task_id:
        err = result.get("code", 0)
        msg = result.get("message", "未知错误")
        raise HTTPException(status_code=502, detail=_friendly_error(err, msg))

    # 存储到内存
    _tasks[task_id] = {
        "status": "running",
        "image_url": "",
        "created_at": time.time(),
    }

    return InpaintSubmitResponse(task_id=task_id)


@router.get("/image-editor/inpaint/{task_id}", response_model=InpaintPollResponse)
async def inpaint_poll(task_id: str):
    """轮询交互编辑任务结果"""
    ak = settings.volc_access_key_id
    sk = settings.volc_secret_access_key
    if not ak or not sk:
        raise HTTPException(status_code=400, detail="火山引擎 AK/SK 未配置")

    cached = _tasks.get(task_id)
    if cached and cached["status"] == "succeeded":
        return InpaintPollResponse(
            status="succeeded",
            image_url=cached.get("image_url", ""),
        )

    params = {
        "req_key": "jimeng_image2image_dream_inpaint",
        "task_id": task_id,
    }

    result = _call_visual_service("CVSync2AsyncGetResult", params, ak, sk)
    logger.info(f"[inpaint poll] task_id={task_id} raw={json.dumps(result, ensure_ascii=False)[:500]}")

    # API 返回的最外层可能也有错误码
    top_code = result.get("code", 0)
    top_msg = result.get("message", "")

    # data 字段可能为 null
    resp_data = result.get("data") or {}
    status = resp_data.get("status", "") if isinstance(resp_data, dict) else ""

    if status == "done":
        # API 返回 image_urls (数组) 或 binary_data_base64 (数组)
        image_urls = resp_data.get("image_urls", [])
        image_url = image_urls[0] if image_urls else ""
        image_b64 = ""
        if not image_url:
            b64_list = resp_data.get("binary_data_base64", [])
            image_b64 = b64_list[0] if b64_list else ""

        _tasks[task_id] = {
            "status": "succeeded",
            "image_url": image_url,
            "image_base64": image_b64,
        }
        return InpaintPollResponse(
            status="succeeded",
            image_url=image_url,
            image_base64=image_b64,
        )
    elif status in ("running", "submitted", "generating", "in_queue", 1, "1"):
        return InpaintPollResponse(status="running")
    else:
        # 尝试从最外层报错
        if top_code != 10000 and top_msg:
            return InpaintPollResponse(
                status="failed",
                message=_friendly_error(top_code, top_msg),
            )
        err_code = resp_data.get("code", -1) if isinstance(resp_data, dict) else -1
        err_msg = resp_data.get("message", "未知错误") if isinstance(resp_data, dict) else (top_msg or "未知错误")
        return InpaintPollResponse(
            status="failed",
            message=_friendly_error(err_code, err_msg),
        )
