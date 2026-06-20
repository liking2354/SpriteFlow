"""
MAGIC 二次处理 — Real-ESRGAN x4 超分 + 缩小派生命名

管线：
  1. 输入 RGBA PNG → 获取 alpha 通道边界框（bbox）
  2. bbox 扩展 24px → 裁剪内容区域
  3. 用可见像素平均 RGB 填充透明区域 → 送 Real-ESRGAN
  4. Real-ESRGAN anime x4 超分 → 4x 放大裁剪区
  5. 将超分结果 alpha_composite 回全尺寸画布
  6. Resize 到 1/2、1/4、1/8（硬=NEAREST/软=BOX）→ 输出透明 PNG

依赖:
  realesrgan-ncnn-vulkan: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan
  模型: realesrgan-x4plus-anime
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# ============================================================================
# 配置常量
# ============================================================================

REAL_ESRGAN_MODEL = "realesrgan-x4plus-anime"
MAGIC_CROP_PADDING = 24

MAGIC_VARIANTS: tuple[dict[str, str | float], ...] = (
    {"key": "half",    "label": "1/2", "scale": 0.5,   "dir": "frames"},
    {"key": "quarter", "label": "1/4", "scale": 0.25,  "dir": "frames-quarter"},
    {"key": "eighth",  "label": "1/8", "scale": 0.125, "dir": "frames-eighth"},
)

MAGIC_RESIZE_MODES: dict[str, dict[str, str | int]] = {
    "hard": {"label": "硬", "resample": Image.NEAREST},
    "soft": {"label": "软", "resample": Image.BOX},
}


@dataclass
class MagicFrameEntry:
    """单帧 MAGIC 处理结果"""
    source_index: int
    cached: bool = False
    size: dict[str, int] = field(default_factory=dict)
    output_size: dict[str, int] = field(default_factory=dict)  # variant → size


@dataclass
class MagicResult:
    """MAGIC 处理完整结果"""
    magic_id: str
    job_label: str
    model: str = REAL_ESRGAN_MODEL
    resize_mode: str = "hard"
    upscale_available: bool = True
    source_size: dict[str, int] = field(default_factory=dict)
    frames: list[MagicFrameEntry] = field(default_factory=list)
    variants: list[dict[str, str | float]] = field(default_factory=lambda: list(MAGIC_VARIANTS))


# ============================================================================
# 工具函数
# ============================================================================

def _average_visible_rgb(image: Image.Image) -> tuple[int, int, int]:
    """计算图像中非透明像素的平均 RGB 颜色"""
    r, g, b, a = image.split()
    alpha_arr = a.point(lambda p: 1 if p > 0 else 0)  # noqa: E731
    total = sum(alpha_arr.getdata())
    if total == 0:
        return (255, 255, 255)
    r_sum = sum(r.getdata()[i] for i, av in enumerate(alpha_arr.getdata()) if av)
    g_sum = sum(g.getdata()[i] for i, av in enumerate(alpha_arr.getdata()) if av)
    b_sum = sum(b.getdata()[i] for i, av in enumerate(alpha_arr.getdata()) if av)
    return (r_sum // total, g_sum // total, b_sum // total)


def _expand_bbox(bbox: tuple[int, int, int, int], padding: int, max_w: int, max_h: int) -> tuple[int, int, int, int]:
    """扩展边界框但不超出图像边界"""
    x0, y0, x1, y1 = bbox
    return (
        max(0, x0 - padding),
        max(0, y0 - padding),
        min(max_w, x1 + padding),
        min(max_h, y1 + padding),
    )


def _prepare_rgb_input(image: Image.Image) -> Image.Image:
    """将 RGBA 图像转为 RGB，用非透明区域平均颜色填充透明区域"""
    rgba = image.convert("RGBA")
    avg_r, avg_g, avg_b = _average_visible_rgb(rgba)
    background = Image.new("RGB", rgba.size, (avg_r, avg_g, avg_b))
    background.paste(rgba, mask=rgba.split()[3])
    return background


def _resize_rgba_premultiplied(
    image: Image.Image, target_size: tuple[int, int], resample: int = Image.LANCZOS
) -> Image.Image:
    """RGBA 预乘 alpha 缩放，避免边缘黑边"""
    return (
        image.convert("RGBA")
        .convert("RGBa")
        .resize(target_size, resample)
        .convert("RGBA")
    )


def _resize_magic_frame(
    image: Image.Image, source_size: tuple[int, int], scale: float, resize_mode: str = "hard"
) -> tuple[Image.Image, tuple[int, int]]:
    """根据 source_size 等比缩放超分结果到目标尺寸"""
    sw, sh = source_size
    target = (round(sw * scale), round(sh * scale))
    mode = MAGIC_RESIZE_MODES.get(resize_mode, MAGIC_RESIZE_MODES["hard"])
    resized = _resize_rgba_premultiplied(image, target, mode["resample"])
    return resized, target


# ============================================================================
# Real-ESRGAN 相关
# ============================================================================

def resolve_realesrgan_binary() -> str | None:
    """查找 realesrgan-ncnn-vulkan 二进制文件"""
    # 1. 环境变量
    env_bin = os.environ.get("REALESRGAN_BIN")
    if env_bin and Path(env_bin).exists():
        return env_bin

    # 2. PATH
    for name in ("realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan.exe"):
        found = shutil.which(name)
        if found:
            return found

    # 3. 预设路径
    candidates = [
        Path("tools/realesrgan-ncnn-vulkan"),
        Path("tools/realesrgan-ncnn-vulkan.exe"),
        Path.home() / "tools/realesrgan-ncnn-vulkan",
    ]
    for p in candidates:
        if p.exists():
            return str(p)

    return None


def resolve_realesrgan_model_dir() -> str | None:
    """查找 Real-ESRGAN 模型目录（包含 realesrgan-x4plus-anime.param 和 .bin）"""
    # 1. 环境变量
    env_dir = os.environ.get("REALESRGAN_MODEL_DIR")
    if env_dir and Path(env_dir).is_dir():
        param = Path(env_dir) / f"{REAL_ESRGAN_MODEL}.param"
        bin_file = Path(env_dir) / f"{REAL_ESRGAN_MODEL}.bin"
        if param.exists() and bin_file.exists():
            return str(env_dir)

    # 2. 预设路径
    candidates = [
        Path("tools/models"),
        Path.home() / "tools/models",
        Path("/usr/local/share/realesrgan/models"),
        Path("/opt/realesrgan/models"),
    ]
    if found_bin := resolve_realesrgan_binary():
        # 二进制同目录下的 models 子目录
        bin_dir = Path(found_bin).parent
        candidates.insert(0, bin_dir / "models")

    for d in candidates:
        param = d / f"{REAL_ESRGAN_MODEL}.param"
        bin_file = d / f"{REAL_ESRGAN_MODEL}.bin"
        if param.exists() and bin_file.exists():
            return str(d)

    return None


def check_realesrgan_available() -> dict[str, Any]:
    """检查 Real-ESRGAN 是否可用"""
    binary = resolve_realesrgan_binary()
    model_dir = resolve_realesrgan_model_dir()
    return {
        "available": bool(binary and model_dir),
        "binary": binary,
        "model_dir": model_dir,
        "model": REAL_ESRGAN_MODEL,
    }


def run_realesrgan(input_path: str, output_path: str) -> None:
    """调用 realesrgan-ncnn-vulkan 进行超分"""
    binary = resolve_realesrgan_binary()
    model_dir = resolve_realesrgan_model_dir()
    if not binary:
        raise RuntimeError(
            "realesrgan-ncnn-vulkan 未找到。请安装: "
            "https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan\n"
            "或设置环境变量 REALESRGAN_BIN 指向二进制文件。"
        )
    if not model_dir:
        raise RuntimeError(
            f"Real-ESRGAN 模型 {REAL_ESRGAN_MODEL} 未找到。\n"
            "请下载模型并设置环境变量 REALESRGAN_MODEL_DIR。"
        )

    cmd = [
        binary,
        "-i", str(input_path),
        "-o", str(output_path),
        "-n", REAL_ESRGAN_MODEL,
        "-m", str(model_dir),
        "-f", "png",
    ]
    logger.info("[magic] running: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        logger.error("[magic] realesrgan failed: stdout=%s stderr=%s", stdout, stderr)
        raise RuntimeError(f"Real-ESRGAN 处理失败 (code={result.returncode}): {stderr or stdout}")


# ============================================================================
# 核心处理
# ============================================================================

def build_magic_upscaled_frame(
    source_rgba: Image.Image,
    ai_input_path: str,
    ai_output_path: str,
) -> tuple[Image.Image, tuple[int, int]]:
    """对单帧执行 Real-ESRGAN x4 超分并重建全尺寸 RGBA 图像

    Args:
        source_rgba: 源 RGBA 图像
        ai_input_path: Real-ESRGAN 输入文件路径
        ai_output_path: Real-ESRGAN 输出文件路径

    Returns:
        (upscaled_full_rgba, source_size)
    """
    sw, sh = source_rgba.size
    source_size = (sw, sh)

    # 1. 获取 alpha 边界框
    bbox = source_rgba.getchannel("A").getbbox()
    if bbox is None:
        # 完全透明 → 返回 4x 空白画布
        return Image.new("RGBA", (sw * 4, sh * 4), (0, 0, 0, 0)), source_size

    # 2. 扩展边界框
    x0, y0, x1, y1 = _expand_bbox(bbox, MAGIC_CROP_PADDING, sw, sh)

    # 3. 裁剪内容区域
    cropped_rgba = source_rgba.crop((x0, y0, x1, y1))
    cw, ch = cropped_rgba.size

    # 4. 准备 RGB 输入（用平均颜色填充透明区域）
    rgb_input = _prepare_rgb_input(cropped_rgba)
    rgb_input.save(ai_input_path, "PNG")
    logger.info("[magic] ai-input saved: %s (%dx%d)", ai_input_path, cw, ch)

    # 5. 调用 Real-ESRGAN
    run_realesrgan(ai_input_path, Path(ai_output_path).parent.as_posix())

    # 6. 加载超分结果
    actual_output = Path(ai_output_path) / Path(ai_input_path).name
    if not actual_output.exists():
        # realesrgan 可能输出到不同路径，搜索一下
        output_dir = Path(ai_output_path)
        pngs = list(output_dir.glob("*.png"))
        if not pngs:
            raise RuntimeError(f"Real-ESRGAN 未生成输出文件: {ai_output_path}")
        actual_output = pngs[0]

    upscaled_cropped = Image.open(actual_output).convert("RGBA")
    uw, uh = upscaled_cropped.size

    # 7. 计算实际缩放比
    scale_x = uw / cw
    scale_y = uh / ch
    logger.info("[magic] upscaled cropped: %dx%d (scale %.2fx%.2f)", uw, uh, scale_x, scale_y)

    # 8. 重建全尺寸 RGBA 画布
    full_w, full_h = round(sw * scale_x), round(sh * scale_y)
    full = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))

    # 9. alpha_composite 贴回正确位置
    paste_x = round(x0 * scale_x)
    paste_y = round(y0 * scale_y)
    # 确保贴入区域存在
    tmp = Image.new("RGBA", full.size, (0, 0, 0, 0))
    tmp.paste(upscaled_cropped, (paste_x, paste_y))
    full = Image.alpha_composite(full, tmp)

    logger.info("[magic] built full upscaled frame: %dx%d", full_w, full_h)
    return full, source_size


def process_single_frame(
    source_path: str,
    source_index: int,
    ai_input_dir: Path,
    ai_output_dir: Path,
    output_base: Path,
    variants: tuple = MAGIC_VARIANTS,
    resize_mode: str = "hard",
    upscale_available: bool = True,
) -> MagicFrameEntry:
    """处理单帧：超分 → 生成三个变体

    如果 Real-ESRGAN 不可用 (upscale_available=False)，跳过超分直接基于原图生成缩小变体。

    Returns MagicFrameEntry 包含处理结果元数据
    """
    source_size = (0, 0)
    output_sizes: dict[str, list[int]] = {}

    with Image.open(source_path) as img:
        source_rgba = img.convert("RGBA")
        source_size = source_rgba.size

        if upscale_available:
            # Real-ESRGAN 超分
            ai_input = str(ai_input_dir / f"frame_{source_index:04d}.png")
            ai_output = str(ai_output_dir)
            try:
                upscaled, src = build_magic_upscaled_frame(source_rgba, ai_input, ai_output)
            except RuntimeError:
                logger.warning("[magic] frame %d upscale failed, using original", source_index)
                upscaled = source_rgba
                src = source_size
        else:
            # 无 Real-ESRGAN，直接用原图
            upscaled = source_rgba
            src = source_size

        # 生成各变体
        for v in variants:
            key = str(v["key"])
            scale = float(v["scale"])
            output_dir = output_base / str(v["dir"])
            output_dir.mkdir(parents=True, exist_ok=True)

            resized, target_size = _resize_magic_frame(upscaled, src, scale, resize_mode)
            out_path = output_dir / f"frame_{source_index:04d}.png"
            resized.save(out_path, "PNG")
            output_sizes[key] = list(target_size)
            logger.info("[magic] variant %s: %dx%d → %s", key, *target_size, out_path)

    return MagicFrameEntry(
        source_index=source_index,
        cached=False,
        size={"width": source_size[0], "height": source_size[1]},
        output_size=output_sizes,
    )


def process_magic(
    source_frames: list[str],
    selected_indices: list[int],
    output_dir: Path,
    resize_mode: str = "hard",
    job_label: str = "",
    progress_callback: callable | None = None,
) -> MagicResult:
    """MAGIC 处理主函数

    Args:
        source_frames: 源帧文件路径列表
        selected_indices: 需要处理的帧索引（从0开始）
        output_dir: 输出根目录
        resize_mode: 缩放模式 "hard"(NEAREST) 或 "soft"(BOX)
        job_label: 任务标签（用于 manifest）
        progress_callback: 进度回调 (current: int, total: int, status: str)

    Returns:
        MagicResult 包含处理结果
    """
    indices = sorted(set(selected_indices))
    total = len(indices)
    if total == 0:
        raise ValueError("未选中任何帧")

    magic_id = hashlib.md5(
        f"{job_label}_{int(time.time())}".encode()
    ).hexdigest()[:12]
    work_dir = output_dir / f"{magic_id}-magic"
    ai_input_dir = work_dir / "ai-input"
    ai_output_dir = work_dir / "ai-output"

    for d in (work_dir, ai_input_dir, ai_output_dir):
        d.mkdir(parents=True, exist_ok=True)

    for v in MAGIC_VARIANTS:
        (work_dir / str(v["dir"])).mkdir(parents=True, exist_ok=True)

    # 检查 Real-ESRGAN 是否可用
    esrgan_status = check_realesrgan_available()
    upscale_available = esrgan_status["available"]
    if not upscale_available:
        logger.warning("[magic] Real-ESRGAN not available, will derive variants from original size (no upscale)")

    logger.info(
        "[magic] start: job=%s magic_id=%s frames=%d mode=%s upscale=%s",
        job_label, magic_id, total, resize_mode, upscale_available,
    )

    result = MagicResult(
        magic_id=magic_id,
        job_label=job_label,
        resize_mode=resize_mode,
        upscale_available=upscale_available,
    )

    first_size = None
    for i, idx in enumerate(indices):
        if idx >= len(source_frames):
            logger.warning("[magic] frame index %d out of range, skip", idx)
            continue

        src_path = source_frames[idx]
        if not os.path.isfile(src_path):
            logger.warning("[magic] source file not found: %s", src_path)
            continue

        if progress_callback:
            progress_callback(i + 1, total, f"处理帧 {idx + 1}/{total}")

        try:
            entry = process_single_frame(
                src_path, idx, ai_input_dir, ai_output_dir,
                work_dir, MAGIC_VARIANTS, resize_mode,
                upscale_available=upscale_available,
            )
            result.frames.append(entry)
            if first_size is None and entry.size:
                first_size = entry.size
        except Exception as e:
            logger.error("[magic] frame %d failed: %s", idx, e)

    if first_size:
        result.source_size = first_size

    # 保存 manifest
    manifest_path = work_dir / "manifest.json"
    manifest_path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("[magic] done: %d frames, manifest=%s", len(result.frames), manifest_path)

    return result


# ============================================================================
# 导出
# ============================================================================

def export_magic_variant(
    work_dir: Path,
    variant_key: str,
    output_path: Path,
) -> Path:
    """导出指定变体的帧序列

    Args:
        work_dir: MAGIC 输出工作目录
        variant_key: "half" / "quarter" / "eighth"
        output_path: 导出目标目录

    Returns:
        导出目录路径
    """
    variant_dir = None
    for v in MAGIC_VARIANTS:
        if v["key"] == variant_key:
            variant_dir = work_dir / str(v["dir"])
            break

    if variant_dir is None or not variant_dir.is_dir():
        raise ValueError(f"变体 {variant_key} 不存在: {variant_dir}")

    output_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for f in sorted(variant_dir.glob("frame_*.png")):
        shutil.copy2(f, output_path / f.name)
        count += 1

    logger.info("[magic] exported %d frames of variant %s to %s", count, variant_key, output_path)
    return output_path
