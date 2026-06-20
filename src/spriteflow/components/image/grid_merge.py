"""
ImageGridMerge 组件 — 图片网格合并

将多张图片按网格排列合并为一张图：
- 支持多个上游节点输入（如多个视频序列帧节点的输出）
- 支持自动/手动指定行列数
- 支持统一单格尺寸、外边距、间距
- 支持像素级(最近邻) / 平滑(Lanczos)缩放
- 支持透明/纯色背景
- 支持自动保存到素材库

输出：单张合并后的网格图 URL
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
from typing import Any

import httpx
from PIL import Image

from ..base import Component, ComponentMeta
from ..utils import save_image_local, download_image

logger = logging.getLogger(__name__)

CELL_SIZE_CHOICES = [0, 32, 48, 64, 96, 128, 192, 256, 384, 512]


async def _download_image(url: str) -> Image.Image:
    """从 URL 下载图片（本地 workflow runs 文件直接读取，避免 HTTP 回环死锁）"""
    local_match = re.search(r"/api/workflow/runs/([^/]+)/outputs/(.+)", url)
    if local_match:
        from spriteflow.config import settings
        run_id, filename = local_match.group(1), local_match.group(2)
        filepath = settings.workflow_runs_dir / run_id / "outputs" / filename
        if filepath.is_file():
            return Image.open(filepath).convert("RGBA")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")


async def _upload_image(image: Image.Image, filename_prefix: str = "grid_merge") -> str:
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

    return url


def _parse_bg_color(color_str: str) -> tuple[int, int, int, int]:
    """解析背景色字符串为 RGBA 元组"""
    if not color_str or color_str == "transparent":
        return (0, 0, 0, 0)

    # 十六进制颜色 #RGB / #RRGGBB / #RRGGBBAA
    hex_match = re.match(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", color_str)
    if hex_match:
        hex_val = hex_match.group(1)
        if len(hex_val) == 3:
            r, g, b = (int(c * 2, 16) for c in hex_val)
            return (r, g, b, 255)
        elif len(hex_val) == 6:
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            return (r, g, b, 255)
        elif len(hex_val) == 8:
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            a = int(hex_val[6:8], 16)
            return (r, g, b, a)

    # 常见颜色名
    color_names = {
        "white": (255, 255, 255, 255),
        "black": (0, 0, 0, 255),
        "red": (255, 0, 0, 255),
        "green": (0, 255, 0, 255),
        "blue": (0, 0, 255, 255),
        "gray": (128, 128, 128, 255),
        "grey": (128, 128, 128, 255),
    }
    return color_names.get(color_str.lower(), (0, 0, 0, 0))


def _merge_grid(
    images: list[Image.Image],
    columns: int,
    rows: int,
    cell_size: int,
    margin: int,
    spacing: int,
    resize_mode: str,
    bg_color: tuple[int, int, int, int],
    align: str,
) -> Image.Image:
    """将多张图片按网格排列合并为一张图

    Args:
        images: 图片列表
        columns: 列数
        rows: 行数
        cell_size: 单格尺寸 (0=使用原图尺寸)
        margin: 外边距
        spacing: 格子间距
        resize_mode: "pixel"=最近邻, "smooth"=Lanczos
        bg_color: 背景色 RGBA
        align: 垂直对齐 "bottom"/"middle"/"top"

    Returns:
        合并后的 PIL Image
    """
    n = len(images)
    if n == 0:
        raise ValueError("没有可合并的图片")

    # 自动计算行列
    if columns <= 0 and rows <= 0:
        # 自动模式：尽量接近正方形
        import math
        columns = math.ceil(math.sqrt(n))
        rows = math.ceil(n / columns)
    elif columns <= 0:
        columns = math.ceil(n / rows)
    elif rows <= 0:
        rows = math.ceil(n / columns)

    # 确保不小于1
    columns = max(1, columns)
    rows = max(1, rows)

    # 选择缩放滤镜
    resample = Image.NEAREST if resize_mode == "pixel" else Image.LANCZOS

    # 处理每张图片：缩放到统一尺寸（如果指定了 cell_size）
    processed: list[Image.Image] = []
    for img in images:
        if cell_size > 0:
            img_resized = img.resize((cell_size, cell_size), resample)
            processed.append(img_resized)
        else:
            # 保持原图尺寸
            processed.append(img.convert("RGBA"))

    # 计算单格尺寸（用于布局）
    if cell_size > 0:
        cell_w = cell_size
        cell_h = cell_size
    else:
        # 使用所有图片中最大的宽高作为单格尺寸
        cell_w = max(img.width for img in processed)
        cell_h = max(img.height for img in processed)

    # 计算画布总尺寸
    canvas_w = margin * 2 + cell_w * columns + spacing * (columns - 1)
    canvas_h = margin * 2 + cell_h * rows + spacing * (rows - 1)

    # 创建画布
    canvas = Image.new("RGBA", (canvas_w, canvas_h), bg_color)

    # 逐张放置
    for i, img in enumerate(processed):
        if i >= columns * rows:
            break

        col = i % columns
        row = i // columns

        # 计算放置位置
        x = margin + col * (cell_w + spacing)
        y = margin + row * (cell_h + spacing)

        # 在格子内对齐
        if align == "bottom":
            y += cell_h - img.height
        elif align == "middle":
            y += (cell_h - img.height) // 2
        # top: 不偏移

        # 水平居中
        x += (cell_w - img.width) // 2

        # 粘贴图片（使用 alpha 通道作为 mask）
        canvas.paste(img, (x, y), img if img.mode == "RGBA" else None)

    return canvas


class ImageGridMergeComponent(Component):
    """图片网格合并组件"""

    @property
    def meta(self) -> ComponentMeta:
        return ComponentMeta(
            component_id="image-grid-merge",
            display_name="图片网格合并",
            category="image",
            subcategory="processing",
            description="将多张图片按网格排列合并为一张图。支持多个上游节点输入（如多个视频序列帧），自动或手动指定行列数，可配置单格尺寸、边距、间距、缩放模式等。输出单张合并后的网格图。",
            version="1.0.0",
            icon="🔲",
            output_type="image_url",
            credential_schema={},
            input_schema={
                "images_list": {
                    "type": "array",
                    "title": "图片列表",
                    "description": "待合并的图片 URL 列表（通过上游连线自动收集，支持多个上游节点同时连接）",
                    "items": {"type": "string", "format": "uri"},
                    "default": [],
                },
                "layout_mode": {
                    "type": "string",
                    "title": "布局模式",
                    "description": "auto=自动计算行列数（尽量接近正方形），manual=手动指定行列数",
                    "enum": ["auto", "manual"],
                    "enumNames": ["自动布局", "手动指定"],
                    "default": "auto",
                },
                "columns": {
                    "type": "integer",
                    "title": "列数",
                    "description": "每行图片数量（0=自动计算，仅在手动模式生效）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 32,
                },
                "rows": {
                    "type": "integer",
                    "title": "行数",
                    "description": "图片行数（0=自动计算，仅在手动模式生效）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 32,
                },
                "cell_size": {
                    "type": "integer",
                    "title": "单格尺寸",
                    "description": "每格的边长像素（0=使用原图尺寸，其他值将等比缩放图片到指定尺寸）",
                    "enum": CELL_SIZE_CHOICES,
                    "enumNames": [
                        "原图尺寸",
                        "32 × 32", "48 × 48", "64 × 64", "96 × 96",
                        "128 × 128", "192 × 192", "256 × 256", "384 × 384", "512 × 512",
                    ],
                    "default": 0,
                },
                "margin": {
                    "type": "integer",
                    "title": "外边距",
                    "description": "画布四周的外边距（像素）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 128,
                },
                "spacing": {
                    "type": "integer",
                    "title": "间距",
                    "description": "格子之间的间距（像素）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 64,
                },
                "resize_mode": {
                    "type": "string",
                    "title": "缩放模式",
                    "description": "pixel=最近邻（像素风/像素画），smooth=Lanczos（平滑缩放）",
                    "enum": ["smooth", "pixel"],
                    "enumNames": ["平滑 (Lanczos)", "像素 (最近邻)"],
                    "default": "smooth",
                },
                "bg_color": {
                    "type": "string",
                    "title": "背景色",
                    "description": "画布背景色（transparent=透明，或十六进制颜色如 #FFFFFF）",
                    "default": "transparent",
                },
                "align": {
                    "type": "string",
                    "title": "垂直对齐",
                    "description": "图片在格子内的垂直对齐方式",
                    "enum": ["bottom", "middle", "top"],
                    "enumNames": ["底部对齐", "居中对齐", "顶部对齐"],
                    "default": "bottom",
                },
                "auto_save": {
                    "type": "boolean",
                    "title": "自动保存到素材库",
                    "description": "执行完成后自动将合并图保存到素材库",
                    "default": False,
                },
            },
            input_required=["images_list"],
        )

    async def validate(self, inputs: dict[str, Any], params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        images_list = inputs.get("images_list", [])
        if not images_list or (isinstance(images_list, list) and len(images_list) == 0):
            errors.append("请提供至少一张图片（images_list 不能为空）")
        return errors

    async def execute(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any],
        credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 参数提取
        def _get(key: str, default: Any = None) -> Any:
            val = params.get(key)
            if val is None:
                val = inputs.get(key)
            if val is None:
                return default
            return val

        def _get_int(key: str, default: int) -> int:
            val = _get(key, default)
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def _get_bool(key: str, default: bool) -> bool:
            val = _get(key, default)
            if isinstance(val, bool):
                return val
            if val is not None:
                return str(val).lower() == "true"
            return default

        # 收集所有图片 URL
        images_list = _get("images_list", [])
        if isinstance(images_list, str):
            # 如果是逗号分隔的字符串（all_urls 格式）
            images_list = [u.strip() for u in images_list.split(",") if u.strip()]
        if not isinstance(images_list, list):
            images_list = [str(images_list)] if images_list else []

        # 也检查 all_urls（上游节点 meta 注入的逗号分隔 URL 字符串）
        all_urls = _get("all_urls", "")
        if all_urls and isinstance(all_urls, str):
            extra_urls = [u.strip() for u in all_urls.split(",") if u.strip()]
            # 合并去重
            for u in extra_urls:
                if u not in images_list:
                    images_list.append(u)

        if not images_list:
            raise ValueError("没有可合并的图片，请确保上游节点已连接并产生输出")

        layout_mode = _get("layout_mode", "auto")
        columns = _get_int("columns", 0)
        rows = _get_int("rows", 0)
        cell_size = _get_int("cell_size", 0)
        margin = max(0, _get_int("margin", 0))
        spacing = max(0, _get_int("spacing", 0))
        resize_mode = _get("resize_mode", "smooth")
        bg_color_str = _get("bg_color", "transparent")
        align = _get("align", "bottom")
        auto_save = _get_bool("auto_save", False)

        # layout_mode=auto 时，如果用户设置了 columns 或 rows，仍然尊重用户设置
        # _merge_grid 内部会处理：两者都为0时自动计算，只设一个时自动推算另一个
        # layout_mode=manual 时行为相同，区别仅在于前端 UI 是否显示行列输入框
        # 无需在此处强制清零 columns/rows

        logger.info(
            "[ImageGridMerge] images=%d layout=%s cols=%d rows=%d cell=%d "
            "margin=%d spacing=%d resize=%s bg=%s align=%s auto_save=%s",
            len(images_list), layout_mode, columns, rows, cell_size,
            margin, spacing, resize_mode, bg_color_str, align, auto_save,
        )

        # 1. 下载所有图片
        images: list[Image.Image] = []
        for i, url in enumerate(images_list):
            try:
                img = await download_image(url)
                images.append(img)
                logger.info("[ImageGridMerge] downloaded %d/%d: %dx%d", i + 1, len(images_list), img.width, img.height)
            except Exception as e:
                logger.warning("[ImageGridMerge] failed to download image %d (%s): %s", i, url[:80], e)

        if not images:
            raise ValueError("所有图片下载失败，请检查图片 URL 是否有效")

        logger.info("[ImageGridMerge] downloaded %d/%d images successfully", len(images), len(images_list))

        # 2. 解析背景色
        bg_color = _parse_bg_color(bg_color_str)

        # 3. 合并网格
        merged = await asyncio.to_thread(
            _merge_grid,
            images,
            columns,
            rows,
            cell_size,
            margin,
            spacing,
            resize_mode,
            bg_color,
            align,
        )

        logger.info(
            "[ImageGridMerge] merged: %dx%d (from %d images)",
            merged.width, merged.height, len(images),
        )

        # 4. 保存合并图到本地
        url = await save_image_local(merged, "grid_merge")
        logger.info("[ImageGridMerge] saved: %s", url[:120])

        # 5. 自动保存到素材库
        if auto_save:
            try:
                from spriteflow.api.deps import get_storage, get_db
                from spriteflow.asset_hub.ingest import IngestPipeline

                storage = get_storage()
                db = get_db()
                pipeline = IngestPipeline(storage, db)

                buf = io.BytesIO()
                merged.save(buf, format="PNG")
                data = buf.getvalue()

                content_hash = hashlib.sha256(data).hexdigest()[:32]
                filename = f"grid_merge_{content_hash}.png"

                asset = await pipeline.ingest(
                    data=data,
                    filename=filename,
                    source="generated",
                    provenance={
                        "source": "workflow:image-grid-merge",
                        "image_count": len(images),
                    },
                )
                logger.info("[ImageGridMerge] auto-saved to asset library: %s", asset.id)
            except Exception as e:
                logger.warning("[ImageGridMerge] auto-save failed: %s", e)

        # 6. 构建输出
        outputs = [{"type": "image_url", "value": url}]

        # 计算实际行列数用于 meta
        import math
        if columns <= 0 and rows <= 0:
            actual_cols = math.ceil(math.sqrt(len(images)))
            actual_rows = math.ceil(len(images) / actual_cols)
        elif columns <= 0:
            actual_cols = math.ceil(len(images) / rows)
            actual_rows = rows
        elif rows <= 0:
            actual_cols = columns
            actual_rows = math.ceil(len(images) / columns)
        else:
            actual_cols = columns
            actual_rows = rows

        logger.info("[ImageGridMerge] done: %dx%d grid, %d images", actual_cols, actual_rows, len(images))
        return {
            "outputs": outputs,
            "meta": {
                "total_images": len(images),
                "columns": actual_cols,
                "rows": actual_rows,
                "canvas_width": merged.width,
                "canvas_height": merged.height,
                "cell_size": cell_size,
                "margin": margin,
                "spacing": spacing,
                "resize_mode": resize_mode,
                "bg_color": bg_color_str,
                "align": align,
            },
        }
