"""
组件共享工具 — 统一文件处理

设计原则：
- 组件生成图片后保存到本地临时目录，返回文件路径（不上传 COS）
- 框架层（workflow_helper._save_outputs_to_local）负责将临时文件复制到 run 输出目录
- 仅当需要调用外部 AI API 时，_refresh_cos_urls 才上传本地文件到 COS

这样消除了"组件上传 COS → 框架从 COS 下载回来"的冗余往返。

临时目录通过 COMPONENTS_TEMP_DIR 环境变量配置，默认为 .cache/components_temp。
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import re
from pathlib import Path

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


def _get_temp_dir() -> Path:
    """获取组件临时输出目录（惰性初始化，从 settings 读取可配置路径）"""
    from spriteflow.config import settings

    d = settings.components_temp_dir
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_local_file_path(value: str) -> bool:
    """判断值是否为本地文件路径（而非 URL）"""
    if not isinstance(value, str) or not value:
        return False
    # URL 协议前缀
    if value.startswith(("http://", "https://", "cos://", "local://", "data:")):
        return False
    # 绝对路径
    if value.startswith("/"):
        return True
    return False


def is_local_workflow_url(url: str) -> bool:
    """判断是否为本地 workflow runs URL（/api/workflow/runs/...）"""
    return bool(url and "/api/workflow/runs/" in url)


async def save_image_local(image: Image.Image, filename_prefix: str = "output") -> str:
    """将 PIL 图片保存到本地临时目录，返回文件路径。

    组件调用此函数替代直接上传 COS。
    框架的 _save_outputs_to_local 会将文件复制到 run 输出目录并生成 HTTP URL。

    Args:
        image: PIL Image 对象
        filename_prefix: 文件名前缀

    Returns:
        本地文件绝对路径，如 {components_temp_dir}/output_abc123.png
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data = buf.getvalue()

    content_hash = hashlib.sha256(data).hexdigest()[:32]
    filename = f"{filename_prefix}_{content_hash}.png"
    filepath = _get_temp_dir() / filename
    filepath.write_bytes(data)

    logger.info("[component_utils] saved locally: %s (%dx%d, %d bytes)",
                filepath, image.width, image.height, len(data))
    return str(filepath)


async def download_image(url_or_path: str) -> Image.Image:
    """下载图片，支持本地文件路径、本地 workflow URL、远程 URL。

    替代各组件中重复的 _download_image 函数。

    Args:
        url_or_path: 本地文件路径 / 本地 workflow URL / 远程 URL

    Returns:
        RGBA 模式的 PIL Image
    """
    if not url_or_path:
        raise ValueError("URL 或路径为空")

    # 1. 本地文件路径（组件 save_image_local 返回的路径）
    if is_local_file_path(url_or_path):
        if os.path.isfile(url_or_path):
            return Image.open(url_or_path).convert("RGBA")
        raise FileNotFoundError(f"本地文件不存在: {url_or_path}")

    # 2. 本地 workflow runs URL（避免 HTTP 回环死锁）
    local_match = re.search(r"/api/workflow/runs/([^/]+)/outputs/(.+)", url_or_path)
    if local_match:
        from spriteflow.config import settings
        run_id, filename = local_match.group(1), local_match.group(2)
        filepath = settings.workflow_runs_dir / run_id / "outputs" / filename
        if filepath.is_file():
            return Image.open(filepath).convert("RGBA")
        # 文件不存在则尝试 HTTP 下载（可能在不同机器上）
        logger.warning("[component_utils] local file not found, trying HTTP: %s", filepath)

    # 3. 远程 URL（COS / 外部 URL）
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url_or_path)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")


async def upload_file_to_cos(file_path: str) -> str | None:
    """将本地文件上传到 COS，返回公网 URL。

    供 _refresh_cos_urls 在需要调用外部 AI API 时使用。

    Args:
        file_path: 本地文件路径

    Returns:
        COS 公网 URL，或 None（上传失败时）
    """
    if not os.path.isfile(file_path):
        logger.error("[component_utils] file not found for COS upload: %s", file_path)
        return None

    data = Path(file_path).read_bytes()
    filename = os.path.basename(file_path)

    from spriteflow.api.deps import get_storage
    from spriteflow.storage.base import StoragePrefix

    storage = get_storage()
    uri = await storage.upload(filename, data, prefix=StoragePrefix.AI_PROCESSED, content_type="image/png")

    try:
        url = await storage.get_presigned_url(uri)
    except Exception:
        url = uri

    logger.info("[component_utils] uploaded to COS: %s → %s", file_path, url[:120])
    return url
