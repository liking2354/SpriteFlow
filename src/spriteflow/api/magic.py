"""
MAGIC 二次处理 API — Real-ESRGAN 超分 + 缩小派生

端点:
  GET    /api/magic/status                       检查 Real-ESRGAN 是否可用
  POST   /api/magic/process                      从视频帧任务处理
  POST   /api/magic/process-upload               从上传帧处理
  GET    /api/magic/{magic_id}/status            查询处理状态
  GET    /api/magic/{magic_id}/frames/{variant}/{filename}  获取处理后帧
  POST   /api/magic/{magic_id}/export/{variant}  导出变体帧为 ZIP
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from PIL import Image

from ..tools.magic_processor import (
    check_realesrgan_available,
    export_magic_variant,
    MAGIC_VARIANTS,
    process_magic,
)

router = APIRouter()

# 输出根目录
_OUTPUT_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "runs" / "magic"
_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# 内存任务状态（简单实现，后续可改为 DB）
_magic_jobs: dict[str, dict] = {}
_magic_lock = threading.Lock()


# ============================================================================
# 请求模型
# ============================================================================

class MagicProcessRequest(BaseModel):
    """从视频帧任务发起的 MAGIC 处理请求"""
    job_id: str = Field(..., description="视频帧任务 ID")
    selected_indices: list[int] = Field(..., description="需要处理的帧索引列表")
    resize_mode: str = Field(default="hard", description="缩放模式: hard(硬/NEAREST) / soft(软/BOX)")
    label: str = Field(default="", description="任务标签")


class MagicUploadRequest(BaseModel):
    """从上传帧发起的 MAGIC 处理请求"""
    selected_indices: list[int] = Field(default_factory=list, description="需要处理的帧索引列表（空=全部）")
    resize_mode: str = Field(default="hard", description="缩放模式: hard(硬/NEAREST) / soft(软/BOX)")
    label: str = Field(default="upload", description="任务标签")


# ============================================================================
# API
# ============================================================================

@router.get("/status")
async def magic_status():
    """检查 Real-ESRGAN 是否可用"""
    return check_realesrgan_available()


@router.post("/process")
async def magic_process(req: MagicProcessRequest):
    """从视频帧任务发起 MAGIC 处理"""
    # 查找视频帧任务目录
    from .video_frames import _DATA_DIR as vf_data_dir, _jobs as vf_jobs

    job_dir = vf_data_dir / req.job_id
    frame_dir = job_dir / "frames"
    if not frame_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"视频帧任务 {req.job_id} 的帧目录不存在")

    source_files = sorted(
        [str(p) for p in frame_dir.glob("frame_*.png")]
    )
    if not source_files:
        raise HTTPException(status_code=404, detail=f"视频帧任务 {req.job_id} 没有帧文件")

    indices = req.selected_indices
    if not indices:
        raise HTTPException(status_code=400, detail="请选择至少一帧")

    job_label = req.label or f"video-frames:{req.job_id}"

    try:
        result = process_magic(
            source_frames=source_files,
            selected_indices=indices,
            output_dir=_OUTPUT_ROOT,
            resize_mode=req.resize_mode,
            job_label=job_label,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "magic_id": result.magic_id,
        "frames_count": len(result.frames),
        "source_size": result.source_size,
        "resize_mode": result.resize_mode,
        "upscale_available": result.upscale_available,
        "variants": [
            {
                "key": v["key"],
                "label": v["label"],
                "scale": v["scale"],
                "output_size": next(
                    (f.output_size.get(v["key"]) for f in result.frames if f.output_size.get(v["key"])),
                    None,
                ),
            }
            for v in MAGIC_VARIANTS
        ],
    }


@router.post("/process-upload")
async def magic_process_upload(
    label: str = "upload",
    resize_mode: str = "hard",
    frames: list[UploadFile] = File(...),
):
    """从上传帧发起 MAGIC 处理（适用于 SpriteSheet 等前端帧）"""
    if not frames:
        raise HTTPException(status_code=400, detail="请上传至少一帧")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_files: list[str] = []

        for i, f in enumerate(frames):
            data = await f.read()
            if not data:
                continue
            src_path = tmp_path / f"frame_{i:04d}.png"
            src_path.write_bytes(data)
            source_files.append(str(src_path))

        if not source_files:
            raise HTTPException(status_code=400, detail="所有帧数据为空")

        try:
            result = process_magic(
                source_frames=source_files,
                selected_indices=list(range(len(source_files))),
                output_dir=_OUTPUT_ROOT,
                resize_mode=resize_mode,
                job_label=label,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {
        "magic_id": result.magic_id,
        "frames_count": len(result.frames),
        "source_size": result.source_size,
        "resize_mode": result.resize_mode,
        "upscale_available": result.upscale_available,
        "variants": [
            {
                "key": v["key"],
                "label": v["label"],
                "scale": v["scale"],
                "output_size": next(
                    (f.output_size.get(v["key"]) for f in result.frames if f.output_size.get(v["key"])),
                    None,
                ),
            }
            for v in MAGIC_VARIANTS
        ],
    }


@router.get("/{magic_id}/status")
async def magic_job_status(magic_id: str):
    """查询 MAGIC 任务状态和结果"""
    work_dir = _OUTPUT_ROOT / f"{magic_id}-magic"
    manifest_path = work_dir / "manifest.json"

    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"MAGIC 任务 {magic_id} 不存在")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 收集变体信息
    variants_info = []
    for v in MAGIC_VARIANTS:
        vdir = work_dir / str(v["dir"])
        frame_count = len(list(vdir.glob("frame_*.png"))) if vdir.is_dir() else 0
        variants_info.append({
            "key": v["key"],
            "label": v["label"],
            "scale": v["scale"],
            "frame_count": frame_count,
            "output_size": next(
                (f["output_size"].get(v["key"]) for f in manifest.get("frames", [])
                 if f.get("output_size", {}).get(v["key"])),
                None,
            ),
        })

    return {
        "magic_id": magic_id,
        "status": "completed",
        "frames_count": manifest.get("frames_count", len(manifest.get("frames", []))),
        "source_size": manifest.get("source_size"),
        "resize_mode": manifest.get("resize_mode"),
        "variants": variants_info,
    }


@router.get("/{magic_id}/frames/{variant_key}/{filename:path}")
async def serve_magic_frame(magic_id: str, variant_key: str, filename: str):
    """提供处理后帧文件（用于前端预览）"""
    work_dir = _OUTPUT_ROOT / f"{magic_id}-magic"
    variant_dir = None
    for v in MAGIC_VARIANTS:
        if v["key"] == variant_key:
            variant_dir = work_dir / str(v["dir"])
            break

    if variant_dir is None or not variant_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"变体 {variant_key} 不存在")

    file_path = variant_dir / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"帧文件不存在: {filename}")

    return FileResponse(str(file_path), media_type="image/png")


@router.get("/{magic_id}/export/{variant_key}")
async def export_magic_variant_endpoint(magic_id: str, variant_key: str):
    """导出变体帧为 ZIP 文件"""
    work_dir = _OUTPUT_ROOT / f"{magic_id}-magic"
    if not work_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"MAGIC 任务 {magic_id} 不存在")

    # 找到变体目录
    variant_dir = None
    for v in MAGIC_VARIANTS:
        if v["key"] == variant_key:
            variant_dir = work_dir / str(v["dir"])
            break

    if variant_dir is None or not variant_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"变体 {variant_key} 不存在")

    # 直接读取帧文件，在内存中构建 ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(variant_dir.glob("frame_*.png")):
            zf.write(str(f), f.name)

    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="magic-{variant_key}-frames.zip"',
        },
    )


# ============================================================================
# 合成 PNG 导出 + 保存到素材库
# ============================================================================

def _merge_frames_to_spritesheet(variant_dir: Path, columns: int) -> bytes:
    """将变体目录下的所有 frame_*.png 合并为合成 PNG

    Args:
        variant_dir: 变体帧目录
        columns: 每行帧数

    Returns:
        PNG 字节数据
    """
    files = sorted(variant_dir.glob("frame_*.png"))
    if not files:
        raise ValueError("变体目录中没有帧文件")

    images: list[Image.Image] = []
    for f in files:
        images.append(Image.open(f).convert("RGBA"))

    # 计算网格尺寸
    cell_w = max(img.width for img in images)
    cell_h = max(img.height for img in images)
    rows = (len(images) + columns - 1) // columns

    canvas_w = cell_w * columns
    canvas_h = cell_h * rows
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    for i, img in enumerate(images):
        row = i // columns
        col = i % columns
        x = col * cell_w + (cell_w - img.width) // 2
        y = row * cell_h + (cell_h - img.height) // 2
        canvas.paste(img, (x, y), img)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/{magic_id}/spritesheet/{variant_key}")
async def magic_spritesheet_export(magic_id: str, variant_key: str, columns: int = Query(default=8, ge=1, le=64)):
    """下载 MAGIC 变体的合成 PNG"""
    work_dir = _OUTPUT_ROOT / f"{magic_id}-magic"
    if not work_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"MAGIC 任务 {magic_id} 不存在")

    variant_dir = None
    for v in MAGIC_VARIANTS:
        if v["key"] == variant_key:
            variant_dir = work_dir / str(v["dir"])
            break

    if variant_dir is None or not variant_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"变体 {variant_key} 不存在")

    try:
        data = _merge_frames_to_spritesheet(variant_dir, columns)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="magic-{variant_key}-sheet.png"',
        },
    )


class MagicSaveToLibraryRequest(BaseModel):
    columns: int = Field(default=8, ge=1, le=64, description="合成每行帧数")


@router.post("/{magic_id}/save-to-library/{variant_key}")
async def magic_save_to_library(
    magic_id: str, variant_key: str, req: MagicSaveToLibraryRequest
):
    """合并 MAGIC 变体帧为合成 PNG 并保存到素材库"""
    work_dir = _OUTPUT_ROOT / f"{magic_id}-magic"
    if not work_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"MAGIC 任务 {magic_id} 不存在")

    variant_dir = None
    for v in MAGIC_VARIANTS:
        if v["key"] == variant_key:
            variant_dir = work_dir / str(v["dir"])
            break

    if variant_dir is None or not variant_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"变体 {variant_key} 不存在")

    try:
        data = _merge_frames_to_spritesheet(variant_dir, req.columns)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 保存到素材库
    from spriteflow.api.deps import get_db, get_storage
    from spriteflow.asset_hub.ingest import IngestPipeline

    storage = get_storage()
    db = get_db()
    pipeline = IngestPipeline(storage, db)

    variant_label = {"half": "1/2", "quarter": "1/4", "eighth": "1/8"}.get(variant_key, variant_key)
    asset = await pipeline.ingest(
        data=data,
        filename=f"magic-{variant_key}-{magic_id[:6]}.png",
        source="generated",
        provenance={
            "source": f"magic:{magic_id}",
            "variant": variant_key,
            "columns": req.columns,
        },
    )
    return {"asset_id": asset.id, "uri": asset.uri, "variant": variant_label}
