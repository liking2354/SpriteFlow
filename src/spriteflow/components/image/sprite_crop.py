"""
SpriteCrop 组件 — 图片精灵智能剪裁

将包含多个游戏角色精灵的合图按网格拆分：
- 支持自动检测行列数（alpha 通道扫描）
- 支持手动指定行列数
- 每格居中显示，统一画布尺寸
- 支持保留原图纯色背景

输出：按顺序返回每张剪裁图的 URL（outputs[0]~outputs[N-1]）
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from typing import Any

import httpx
import numpy as np
from PIL import Image

from ..base import Component, ComponentMeta
from ..utils import save_image_local, download_image

logger = logging.getLogger(__name__)

SIZE_CHOICES = [
    {"value": "64", "label": "64 × 64"},
    {"value": "128", "label": "128 × 128"},
    {"value": "256", "label": "256 × 256"},
    {"value": "512", "label": "512 × 512"},
    {"value": "1024", "label": "1024 × 1024"},
]

COLUMNS_CHOICES = [
    {"value": 0, "label": "自动检测"},
    {"value": 1, "label": "1 列"},
    {"value": 2, "label": "2 列"},
    {"value": 3, "label": "3 列"},
    {"value": 4, "label": "4 列"},
]

ROWS_CHOICES = [
    {"value": 0, "label": "自动检测"},
    {"value": 1, "label": "1 行"},
    {"value": 2, "label": "2 行"},
    {"value": 3, "label": "3 行"},
]


# ---- 网格检测 ----

def _detect_gap_positions(
    alpha: np.ndarray,
    axis: int,
    threshold: int = 16,
    gap_ratio: float = 0.03,
    min_gap_width: int = 2,
) -> list[int]:
    """沿指定轴扫描 alpha 通道，找出透明间隙的分割位置

    Args:
        alpha: alpha 通道数组 (H, W)
        axis: 0=按行扫描, 1=按列扫描
        threshold: 透明判定阈值（降低以提高敏感度）
        gap_ratio: 连续透明像素超过该比例才视为间隙
        min_gap_width: 最小间隙宽度

    Returns:
        分割线位置列表（像素坐标）
    """
    h, w = alpha.shape
    length = h if axis == 0 else w
    total = w if axis == 0 else h

    gap_threshold = int(total * gap_ratio)

    # 统计每行/列的非透明像素数
    non_transparent = (alpha > threshold).sum(axis=1 - axis)

    # 找出连续透明行/列的区间
    gaps: list[tuple[int, int]] = []
    gap_start = -1
    for i in range(length):
        if non_transparent[i] <= gap_threshold:
            if gap_start == -1:
                gap_start = i
        else:
            if gap_start != -1:
                if i - gap_start > min_gap_width:
                    gaps.append((gap_start, i - 1))
                gap_start = -1
    # 处理末尾的间隙
    if gap_start != -1 and length - gap_start > min_gap_width:
        gaps.append((gap_start, length - 1))

    # 计算每个间隙的中点作为分割线
    positions = [(g[0] + g[1]) // 2 for g in gaps]
    return positions


def _detect_content_boundaries(
    image: Image.Image,
    axis: int,
    content_threshold: int = 30,
) -> list[int]:
    """基于 RGB 内容变化检测精灵边界（作为 alpha 检测的补充）

    将图片转为灰度图，计算相邻行/列的像素差异，差异峰值处即为精灵分界。

    Args:
        image: 源图片
        axis: 0=按行检测, 1=按列检测
        content_threshold: 内容差异阈值

    Returns:
        分割线位置列表
    """
    rgb = image.convert("RGB")
    arr = np.array(rgb)
    gray = np.mean(arr, axis=2)  # (H, W) 灰度

    if axis == 0:
        # 按行：每行的平均灰度
        profile = gray.mean(axis=1)
    else:
        # 按列：每列的平均灰度
        profile = gray.mean(axis=0)

    # 计算相邻列/行的灰度差异（一阶差分）
    if len(profile) < 3:
        return []

    diff = np.abs(np.diff(profile))

    # 找差异峰值位置
    length = len(diff)
    if length < 3:
        return []

    mean_diff = float(np.mean(diff))
    std_diff = float(np.std(diff))
    peak_threshold = mean_diff + std_diff * 1.5

    # 找显著峰值
    peaks: list[int] = []
    for i in range(1, length - 1):
        if (
            diff[i] > peak_threshold
            and diff[i] > content_threshold
            and diff[i] >= diff[i - 1]
            and diff[i] >= diff[i + 1]
        ):
            peaks.append(i)

    # 合并相邻峰值（距离 < 5px 的合并）
    if not peaks:
        return []

    merged: list[int] = [peaks[0]]
    for p in peaks[1:]:
        if p - merged[-1] > 5:
            merged.append(p)
        else:
            merged[-1] = (merged[-1] + p) // 2

    return merged


def _detect_grid(
    image: Image.Image,
    threshold: int = 16,
) -> tuple[int, int, list[tuple[int, int, int, int]]] | None:
    """自动检测精灵图网格（alpha 间隙 + 内容边界双重检测）

    Returns:
        (cols, rows, cells) 或 None。
        cells: [(left, top, right, bottom), ...] 每个格子的裁剪边界
    """
    if image.mode not in ("RGBA", "LA"):
        image = image.convert("RGBA")

    alpha = np.array(image.split()[-1])
    w, h = image.size

    # 检测列间隙（alpha 优先，内容检测补充）
    col_boundaries = _detect_gap_positions(alpha, axis=1, threshold=threshold)
    if not col_boundaries:
        # 尝试内容检测
        col_boundaries = _detect_content_boundaries(image, axis=1)
        logger.info("[SpriteCrop] using content-based column detection, found %d seams", len(col_boundaries))
    else:
        logger.info("[SpriteCrop] alpha-based column detection: %d gaps", len(col_boundaries))

    # 检测行间隙
    row_boundaries = _detect_gap_positions(alpha, axis=0, threshold=threshold)
    if not row_boundaries:
        row_boundaries = _detect_content_boundaries(image, axis=0)
        logger.info("[SpriteCrop] using content-based row detection, found %d seams", len(row_boundaries))

    # 构建完整边界列表
    col_bounds = [0] + col_boundaries + [w]
    col_bounds.sort()
    cols = len(col_bounds) - 1

    row_bounds = [0] + row_boundaries + [h]
    row_bounds.sort()
    rows = len(row_bounds) - 1

    if cols < 1 or rows < 1:
        logger.warning("[SpriteCrop] grid detection found no cells (cols=%d, rows=%d)", cols, rows)
        return None

    # 计算每个 cell
    cells: list[tuple[int, int, int, int]] = []
    for ri in range(rows):
        for ci in range(cols):
            left = col_bounds[ci]
            right = col_bounds[ci + 1]
            top = row_bounds[ri]
            bottom = row_bounds[ri + 1]
            cells.append((left, top, right, bottom))

    # 验证：所有 cell 尺寸偏差放宽到 35%
    cell_widths = [c[2] - c[0] for c in cells]
    cell_heights = [c[3] - c[1] for c in cells]
    if not cell_widths or not cell_heights:
        return None

    avg_w = sum(cell_widths) / len(cell_widths)
    avg_h = sum(cell_heights) / len(cell_heights)
    if avg_w < 10 or avg_h < 10:
        logger.warning("[SpriteCrop] cell too small: avg_w=%.1f avg_h=%.1f", avg_w, avg_h)
        return None

    max_deviation = 0.0
    for cw in cell_widths:
        deviation = abs(cw - avg_w) / avg_w if avg_w > 0 else 0
        max_deviation = max(max_deviation, deviation)
    for ch in cell_heights:
        deviation = abs(ch - avg_h) / avg_h if avg_h > 0 else 0
        max_deviation = max(max_deviation, deviation)

    if max_deviation > 0.35:
        logger.warning("[SpriteCrop] cell size deviation too high: %.1f%%", max_deviation * 100)
        return None

    logger.info(
        "[SpriteCrop] auto-detected grid: %d cols × %d rows, %d cells (max_deviation=%.1f%%)",
        cols, rows, len(cells), max_deviation * 100,
    )
    return cols, rows, cells


def _find_best_split(
    alpha: np.ndarray,
    axis: int,
    center: int,
    search_range: int,
    threshold: int = 16,
) -> int:
    """在 center 附近搜索内容最少的行/列作为最佳切割点

    Args:
        alpha: alpha 通道数组 (H, W)
        axis: 0=垂直切割（搜索列）, 1=水平切割（搜索行）
        center: 初始等分中心位置
        search_range: 搜索范围（±像素）
        threshold: 透明判定阈值

    Returns:
        最佳切割位置（像素坐标）
    """
    h, w = alpha.shape
    max_pos = w if axis == 0 else h
    lo = max(0, center - search_range)
    hi = min(max_pos - 1, center + search_range)

    if hi <= lo:
        return center

    # 计算搜索范围内每行/列的非透明像素数
    if axis == 0:
        # 列：统计每列非透明像素
        scores = np.array([(alpha[:, x] > threshold).sum() for x in range(lo, hi + 1)])
    else:
        # 行：统计每行非透明像素
        scores = np.array([(alpha[y, :] > threshold).sum() for y in range(lo, hi + 1)])

    if len(scores) == 0:
        return center

    # 找到内容最少的连续区域（不仅是单个像素，找最低谷的中心）
    min_idx = int(np.argmin(scores))
    # 在最低点附近找连续低谷的中点
    lo_idx = min_idx
    hi_idx = min_idx
    while lo_idx > 0 and scores[lo_idx - 1] <= scores[min_idx] * 1.2:
        lo_idx -= 1
    while hi_idx < len(scores) - 1 and scores[hi_idx + 1] <= scores[min_idx] * 1.2:
        hi_idx += 1

    best_local = (lo_idx + hi_idx) // 2
    return lo + best_local


def _build_manual_grid(
    w: int, h: int, cols: int, rows: int,
    image: Image.Image | None = None,
) -> list[tuple[int, int, int, int]]:
    """根据指定行列数构建网格，支持内容感知边界调整

    当提供 image 参数时，会在等分边界附近搜索内容最少的像素行/列，
    避免切割到精灵本身。无 image 时退回纯等分。
    """
    cell_w = w // cols
    cell_h = h // rows

    if image is None or image.mode not in ("RGBA", "LA"):
        # 无 alpha 信息，退回简单等分
        cells = []
        for ri in range(rows):
            for ci in range(cols):
                left = ci * cell_w
                top = ri * cell_h
                right = w if ci == cols - 1 else (ci + 1) * cell_w
                bottom = h if ri == rows - 1 else (ri + 1) * cell_h
                cells.append((left, top, right, bottom))
        return cells

    alpha = np.array(image.split()[-1])

    # 内容感知列边界
    col_bounds = [0]
    search_range = max(1, cell_w // 3)  # 搜索范围：格宽的 1/3
    for ci in range(1, cols):
        center = ci * cell_w
        best = _find_best_split(alpha, axis=0, center=center, search_range=search_range)
        col_bounds.append(best)
    col_bounds.append(w)

    # 内容感知行边界
    row_bounds = [0]
    search_range = max(1, cell_h // 3)
    for ri in range(1, rows):
        center = ri * cell_h
        best = _find_best_split(alpha, axis=1, center=center, search_range=search_range)
        row_bounds.append(best)
    row_bounds.append(h)

    # 确保边界单调递增且不重叠
    for i in range(1, len(col_bounds)):
        if col_bounds[i] <= col_bounds[i - 1]:
            col_bounds[i] = col_bounds[i - 1] + 1
    for i in range(1, len(row_bounds)):
        if row_bounds[i] <= row_bounds[i - 1]:
            row_bounds[i] = row_bounds[i - 1] + 1

    cells = []
    for ri in range(rows):
        for ci in range(cols):
            left = col_bounds[ci]
            right = col_bounds[ci + 1]
            top = row_bounds[ri]
            bottom = row_bounds[ri + 1]
            cells.append((left, top, right, bottom))

    logger.info(
        "[SpriteCrop] content-aware grid: cols=%s rows=%s",
        [col_bounds[i] for i in range(cols)],
        [row_bounds[i] for i in range(rows)],
    )
    return cells


# ---- 内容感知紧致裁剪 ----

def _find_content_bbox(
    cell_alpha: np.ndarray,
    threshold: int,
) -> tuple[int, int, int, int] | None:
    """在 alpha 区域内搜索非透明内容的包围盒（相对坐标）

    Returns:
        (top, bottom, left, right) 相对坐标，或 None 表示无内容
    """
    h_cell, w_cell = cell_alpha.shape
    non_transparent = cell_alpha > threshold

    rows_with = non_transparent.any(axis=1)
    cols_with = non_transparent.any(axis=0)

    if not rows_with.any() or not cols_with.any():
        return None

    idx_r = np.where(rows_with)[0]
    idx_c = np.where(cols_with)[0]
    return (int(idx_r[0]), int(idx_r[-1]) + 1, int(idx_c[0]), int(idx_c[-1]) + 1)


def _tighten_cell_bounds(
    image: Image.Image,
    cell_bounds: tuple[int, int, int, int],
    margin: int = 4,
) -> tuple[int, int, int, int]:
    """多阈值自适应紧致裁剪：用多个 alpha 阈值尝试找到最合适的精灵边界

    在给定的矩形区域内，通过多级阈值扫描找到一致的内容边界，
    确保裁剪框刚好包围精灵内容，不会残留相邻精灵的像素，
    也不会过度裁剪掉有效内容。

    Args:
        image: 源图片（RGBA）
        cell_bounds: 初始裁剪边界 (left, top, right, bottom)
        margin: 裁剪后额外保留的边距

    Returns:
        收紧后的裁剪边界
    """
    if image.mode not in ("RGBA", "LA"):
        return cell_bounds

    alpha = np.array(image.split()[-1])
    left, top, right, bottom = cell_bounds

    # 裁剪出该格子的 alpha 区域
    cell_alpha = alpha[top:bottom, left:right]
    h_cell, w_cell = cell_alpha.shape

    if h_cell == 0 or w_cell == 0:
        return cell_bounds

    # 多阈值尝试：从宽松到严格
    thresholds = [8, 16, 32, 64, 96]
    best_bbox: tuple[int, int, int, int] | None = None

    for thr in thresholds:
        bbox = _find_content_bbox(cell_alpha, thr)
        if bbox is not None:
            best_bbox = bbox
            # 第一个找到的（最宽松）通常最合适
            break

    if best_bbox is None:
        # 尝试用 RGB 灰度变化检测（完全不透明图）
        return cell_bounds

    btop, bbottom, bleft, bright = best_bbox

    # 用后续更严格的阈值验证边界稳定性
    for thr in thresholds[thresholds.index(8) + 1:]:
        bbox2 = _find_content_bbox(cell_alpha, thr)
        if bbox2 is None:
            continue
        t2, b2, l2, r2 = bbox2
        # 如果严格阈值下边界变化不大，说明边界明确
        if (
            abs(t2 - btop) < 5 and abs(b2 - bbottom) < 5
            and abs(l2 - bleft) < 5 and abs(r2 - bright) < 5
        ):
            btop, bbottom, bleft, bright = t2, b2, l2, r2

    # 加入 margin
    tight_top = max(0, btop - margin)
    tight_bottom = min(h_cell, bbottom + margin)
    tight_left = max(0, bleft - margin)
    tight_right = min(w_cell, bright + margin)

    # 如果收紧后尺寸变化不大（<10%），则保留原边界（避免过度裁剪）
    orig_area = (right - left) * (bottom - top)
    tight_area = (tight_right - tight_left) * (tight_bottom - tight_top)
    if orig_area > 0 and tight_area / orig_area > 0.9:
        return cell_bounds

    return (
        left + tight_left,
        top + tight_top,
        left + tight_right,
        top + tight_bottom,
    )


# ---- 背景色检测 ----

def _detect_bg_color(image: Image.Image, sample_size: int = 5) -> tuple[int, int, int]:
    """从图像四角采样检测纯色背景色"""
    if image.mode not in ("RGBA", "RGB"):
        image = image.convert("RGBA")
    rgb = image.convert("RGB")
    w, h = image.size
    corners = [
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
        (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
    ]
    samples = []
    for cx, cy in corners:
        region = rgb.crop((
            max(0, cx - sample_size // 2),
            max(0, cy - sample_size // 2),
            min(w, cx + sample_size // 2 + 1),
            min(h, cy + sample_size // 2 + 1),
        ))
        arr = np.array(region)
        avg = arr.mean(axis=(0, 1))
        samples.append(tuple(int(v) for v in avg))

    # 返回最常见的颜色
    from collections import Counter
    rounded = [tuple(round(v / 10) * 10 for v in s) for s in samples]
    most_common = Counter(rounded).most_common(1)[0][0]
    return most_common


# ---- 单格处理 ----

def _process_cell(
    image: Image.Image,
    cell_bounds: tuple[int, int, int, int],
    output_size: int,
    keep_bg: bool,
    bg_color: tuple[int, int, int],
    vertical_align: bool = True,
    auto_trim: bool = True,
) -> Image.Image:
    """处理单个格子：裁剪 → 自动修边 → 居中 → 缩放 → 放置到统一画布

    auto_trim 分两步：
      1. Alpha 通道检测（透明 PNG 精灵图）
      2. 颜色差异检测（纯色背景不透明图，回退方案）

    Args:
        image: 源图片
        cell_bounds: 裁剪边界
        output_size: 输出画布尺寸
        keep_bg: 是否保留背景色
        bg_color: 背景色（用于画布填充 + 颜色法 auto_trim）
        vertical_align: 是否垂直居中（精灵可能在格子中偏上/偏下）
        auto_trim: 是否自动裁剪内容背景边缘（去掉格子内精灵周围的纯色区域）
    """
    left, top, right, bottom = cell_bounds

    # 裁剪精灵区域
    sprite = image.crop((left, top, right, bottom))
    sw, sh = sprite.size
    cell_w, cell_h = sw, sh  # 保存原始尺寸用于日志

    trimmed = False

    if auto_trim:
        # ── 方法 1：Alpha 通道检测（适合带透明通道的精灵图）──
        if sprite.mode in ("RGBA", "LA"):
            sprite_alpha = np.array(sprite.split()[-1])
            content_mask = sprite_alpha > 16
            if content_mask.any():
                rows = content_mask.any(axis=1)
                cols = content_mask.any(axis=0)
                if rows.any() and cols.any():
                    idx_r = np.where(rows)[0]
                    idx_c = np.where(cols)[0]
                    trim_left = int(idx_c[0])
                    trim_top = int(idx_r[0])
                    trim_right = int(idx_c[-1]) + 1
                    trim_bottom = int(idx_r[-1]) + 1
                    if trim_left > 2 or trim_top > 2 or trim_right < sw - 2 or trim_bottom < sh - 2:
                        sprite = sprite.crop((
                            max(0, trim_left - 2),
                            max(0, trim_top - 2),
                            min(sw, trim_right + 2),
                            min(sh, trim_bottom + 2),
                        ))
                        sw, sh = sprite.size
                        trimmed = True
                        logger.info(
                            "[SpriteCrop] alpha-based auto_trim: %dx%d → %dx%d (cell=%dx%d)",
                            cell_w, cell_h, sw, sh, cell_w, cell_h,
                        )

        # ── 方法 2：颜色差异检测（适合纯色背景不透明图，alpha 无法区分时回退）──
        if not trimmed:
            sprite_rgb = np.array(sprite.convert("RGB"))
            bg_arr = np.array(bg_color, dtype=np.int32)
            # 每个像素与背景色的最大通道差异
            diff = np.abs(sprite_rgb.astype(np.int32) - bg_arr).max(axis=2)
            # 差异 > 30 视为前景内容
            content_mask = diff > 30
            if content_mask.any():
                rows = content_mask.any(axis=1)
                cols = content_mask.any(axis=0)
                if rows.any() and cols.any():
                    idx_r = np.where(rows)[0]
                    idx_c = np.where(cols)[0]
                    trim_left = int(idx_c[0])
                    trim_top = int(idx_r[0])
                    trim_right = int(idx_c[-1]) + 1
                    trim_bottom = int(idx_r[-1]) + 1
                    # 只在实际有裁剪空间时生效
                    if trim_left > 2 or trim_top > 2 or trim_right < sw - 2 or trim_bottom < sh - 2:
                        margin = 2
                        sprite = sprite.crop((
                            max(0, trim_left - margin),
                            max(0, trim_top - margin),
                            min(sw, trim_right + margin),
                            min(sh, trim_bottom + margin),
                        ))
                        sw, sh = sprite.size
                        trimmed = True
                        logger.info(
                            "[SpriteCrop] color-based auto_trim: %dx%d → %dx%d (bg=%s)",
                            cell_w, cell_h, sw, sh, bg_color,
                        )

    # 创建画布
    if keep_bg:
        canvas = Image.new("RGBA", (output_size, output_size), (*bg_color, 255))
    else:
        canvas = Image.new("RGBA", (output_size, output_size), (0, 0, 0, 0))

    # 等比缩放适配画布
    max_dim = max(sw, sh)
    if max_dim > 0:
        scale = output_size / max_dim
        new_w = max(1, int(sw * scale))
        new_h = max(1, int(sh * scale))
    else:
        new_w, new_h = output_size, output_size

    sprite = sprite.resize((new_w, new_h), Image.LANCZOS)

    # 居中放置（水平 + 垂直）
    x = (output_size - new_w) // 2
    y = (output_size - new_h) // 2

    if vertical_align:
        # 精灵垂直底部对齐：角色脚部贴画布底部，保证不同身高精灵站在同一地面线
        bottom_margin = int(output_size * 0.02)  # 2% 底部留白
        y = output_size - new_h - bottom_margin
        y = max(0, y)

    canvas.paste(sprite, (x, y), sprite if sprite.mode == "RGBA" else None)

    return canvas


# ---- 网络 & 存储 ----

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


async def _upload_image(image: Image.Image, filename_prefix: str = "crop") -> str:
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


# ---- Component ----

class SpriteCropComponent(Component):
    """图片精灵智能剪裁组件"""

    @property
    def meta(self) -> ComponentMeta:
        return ComponentMeta(
            component_id="image-sprite-crop",
            display_name="图片精灵剪裁",
            category="image",
            subcategory="image",
            description="将包含多个游戏角色精灵图的合图按网格智能拆分，自动检测行列数，统一输出尺寸。输出为精灵图数组，下游节点通过连线引用 outputs[0]~outputs[N-1]",
            version="1.0.0",
            icon="✂️",
            output_type="image_batch",
            credential_schema={},
            input_schema={
                "image_url": {
                    "type": "string",
                    "title": "输入图片",
                    "description": "待剪裁的精灵合图 URL（支持上游连线输入）",
                    "format": "uri",
                },
                "columns": {
                    "type": "integer",
                    "title": "列数",
                    "description": "每行精灵数量，0=自动检测",
                    "enum": [c["value"] for c in COLUMNS_CHOICES],
                    "enumNames": [c["label"] for c in COLUMNS_CHOICES],
                    "default": 0,
                },
                "rows": {
                    "type": "integer",
                    "title": "行数",
                    "description": "精灵行数，0=自动检测",
                    "enum": [r["value"] for r in ROWS_CHOICES],
                    "enumNames": [r["label"] for r in ROWS_CHOICES],
                    "default": 0,
                },
                "output_size": {
                    "type": "string",
                    "title": "输出尺寸",
                    "description": "每格输出画布的边长",
                    "enum": [s["value"] for s in SIZE_CHOICES],
                    "enumNames": [s["label"] for s in SIZE_CHOICES],
                    "default": "512",
                },
                "keep_bg": {
                    "type": "boolean",
                    "title": "保留背景",
                    "description": "保留原图纯色背景（关闭则为透明背景）",
                    "default": True,
                },
                "auto_trim": {
                    "type": "boolean",
                    "title": "自动裁剪背景边缘",
                    "description": "自动去除精灵格子内的纯色背景空白区域，裁剪后精灵居中显示",
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

        # 安全获取参数（0 是合法值，不能用 or 短路）
        def _get_int(key: str, default: int) -> int:
            merged = inputs.get(key) if inputs.get(key) is not None else params.get(key)
            if merged is not None:
                try:
                    return int(merged)
                except (ValueError, TypeError):
                    pass
            return default

        def _get_bool(key: str, default: bool) -> bool:
            merged = inputs.get(key) if inputs.get(key, None) is not None else params.get(key)
            if isinstance(merged, bool):
                return merged
            if merged is not None:
                return str(merged).lower() == "true"
            return default

        columns = _get_int("columns", 0)
        rows = _get_int("rows", 0)
        output_size = _get_int("output_size", 512)
        keep_bg = _get_bool("keep_bg", True)
        auto_trim = _get_bool("auto_trim", True)

        logger.info(
            "[SpriteCrop] image=%s cols=%d rows=%d size=%d keep_bg=%s auto_trim=%s",
            image_url[:120], columns, rows, output_size, keep_bg, auto_trim,
        )

        # 1. 下载图片
        image = await download_image(image_url)
        logger.info("[SpriteCrop] downloaded: %dx%d", image.width, image.height)

        # 2. 检测/构建网格
        cells: list[tuple[int, int, int, int]]
        detected_cols: int = 0
        detected_rows: int = 0

        if columns == 0 and rows == 0:
            result = await asyncio.to_thread(_detect_grid, image)
            if result is not None:
                detected_cols, detected_rows, cells = result
            else:
                logger.warning("[SpriteCrop] auto-detection failed, falling back to 1×1")
                cells = _build_manual_grid(image.width, image.height, 1, 1, image=image)
                detected_cols, detected_rows = 1, 1
        else:
            cols = columns if columns > 0 else 1
            rows_count = rows if rows > 0 else 1
            cells = _build_manual_grid(image.width, image.height, cols, rows_count, image=image)
            detected_cols, detected_rows = cols, rows_count

        actual_cols = detected_cols if columns == 0 else columns
        actual_rows = detected_rows if rows == 0 else rows
        logger.info(
            "[SpriteCrop] grid: %d cols × %d rows = %d cells",
            actual_cols, actual_rows, len(cells),
        )

        # 3. 检测背景色（auto_trim 用颜色差异法时需要准确的背景色，因此不再仅限于 keep_bg=True）
        bg_color: tuple[int, int, int] = (255, 255, 255)
        if keep_bg or auto_trim:
            bg_color = await asyncio.to_thread(_detect_bg_color, image)
            logger.info("[SpriteCrop] detected bg color: %s", bg_color)

        # 4. 紧致裁剪每个格子（去除相邻精灵残留）
        tightened_cells = await asyncio.to_thread(
            lambda: [_tighten_cell_bounds(image, cell) for cell in cells],
        )
        logger.info("[SpriteCrop] tightened %d cells", len(tightened_cells))

        # 5. 处理每个格子
        processed = await asyncio.to_thread(
            lambda: [
                _process_cell(image, cell, output_size, keep_bg, bg_color, auto_trim=auto_trim)
                for cell in tightened_cells
            ],
        )
        logger.info("[SpriteCrop] processed %d cells", len(processed))

        # 6. 逐个保存到本地
        urls: list[str] = []
        for i, img in enumerate(processed):
            url = await save_image_local(img, f"crop_{i}")
            urls.append(url)
            logger.info("[SpriteCrop] cell %d saved: %s", i, url[:120])

        # 7. 构建输出（每格一张图，下游通过 image_index 选择）
        outputs = [
            {"type": "image_url", "value": url}
            for url in urls
        ]

        logger.info("[SpriteCrop] done: %d images", len(outputs))
        return {
            "outputs": outputs,
            "meta": {
                "total": len(outputs),
                "columns": actual_cols,
                "rows": actual_rows,
                "all_urls": ",".join(urls),
            },
        }
