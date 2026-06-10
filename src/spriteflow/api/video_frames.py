"""视频序列帧 API — 独立模块

端点：
  POST   /api/video-frames/probe             上传视频 → 返回视频元数据（时长/分辨率/帧率）
  POST   /api/video-frames/jobs              上传视频 + 参数 → 创建抽帧任务
  GET    /api/video-frames/jobs/{job_id}      查询任务状态
  GET    /api/video-frames/jobs/{job_id}/result  下载结果 (PNG / ZIP)
  GET    /api/video-frames/jobs/{job_id}/index   获取索引 JSON
  GET    /api/video-frames/jobs/{job_id}/frames  获取单帧文件列表
  POST   /api/video-frames/jobs/{job_id}/crop    裁剪帧并重新合成
  DELETE /api/video-frames/jobs/{job_id}      删除任务及文件
  POST   /api/video-frames/matte              AI 抠图单张图片
  POST   /api/video-frames/watermark          创建水印去除任务
  GET    /api/video-frames/watermark/{job_id} 查询水印任务状态
  GET    /api/video-frames/watermark/{job_id}/result  下载去水印视频
  DELETE /api/video-frames/watermark/{job_id} 删除水印任务
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image as PILImage

from ..nodes.extract_frames import (
    _find_ffmpeg,
    _find_ffprobe,
    get_video_info,
    compute_layout,
    compose_sprite_sheet,
)

# ---------- 配置 ----------
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".webm", ".mkv", ".flv"}
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_VIDEO_MB = 200
MAX_IMAGE_MB = 20

# 运行时目录：与项目 runs 同级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DATA_DIR = _PROJECT_ROOT / "runs" / "video_frames"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()

# ---------- 内存任务存储 ----------
_jobs: dict[str, dict] = {}          # 抽帧任务
_wm_jobs: dict[str, dict] = {}       # 水印任务


def _job_dir(job_id: str) -> Path:
    d = _DATA_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ============ 视频探针 ============

@router.post("/video-frames/probe")
async def probe_video(file: UploadFile = File(...)):
    """上传视频文件，返回视频元数据（时长/分辨率/帧率/编码）"""
    if not file.filename:
        raise HTTPException(400, "请上传视频文件")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(400, f"不支持的格式: {ext}")

    content = await file.read()
    if len(content) > MAX_VIDEO_MB * 1024 * 1024:
        raise HTTPException(400, f"文件过大，限制 {MAX_VIDEO_MB}MB")

    # 写入临时文件用于 ffprobe 探测
    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp.write(content)
        tmp.close()
        info = get_video_info(tmp.name)
        return {
            "duration": info["duration"],
            "width": info["width"],
            "height": info["height"],
            "original_fps": info["fps"],
            "frame_count": info["frame_count"],
            "filename": file.filename,
            "size_mb": round(len(content) / (1024 * 1024), 2),
        }
    except Exception as e:
        raise HTTPException(500, f"视频探测失败: {str(e)}")
    finally:
        os.unlink(tmp.name)


# ============ 抽帧任务 ============

def _run_extraction_sync(job_id: str, video_path: str, params: dict):
    """后台线程：执行抽帧 + 合成 Sprite Sheet"""
    try:
        jd = _job_dir(job_id)
        fps = params.get("fps", 8)
        max_frames = params.get("max_frames", 16)
        start_sec = params.get("start_sec", 0.0)
        end_sec = params.get("end_sec", 0.0)
        spacing = params.get("spacing", 4)
        layout_mode = params.get("layout_mode", "auto_square")
        columns = params.get("columns", 8)
        crop_left = params.get("crop_left", 0)
        crop_right = params.get("crop_right", 0)
        crop_top = params.get("crop_top", 0)
        crop_bottom = params.get("crop_bottom", 0)

        ffmpeg = _find_ffmpeg()

        # ffprobe 探测
        video_info: dict | None = None
        try:
            video_info = get_video_info(video_path)
        except Exception:
            pass

        tmp_dir = tempfile.mkdtemp(prefix="sf_vf_")
        try:
            duration = video_info["duration"] if video_info else 0.0
            use_timestamp = video_info is not None and duration > 0

            if use_timestamp:
                effective_end = end_sec if end_sec > 0 else duration
                effective_start = max(0.0, min(start_sec, duration))
                effective_end = max(effective_start, min(effective_end, duration))
                if effective_end <= effective_start:
                    effective_end = duration
                interval = 1.0 / fps
                timestamps: list[float] = []
                t = effective_start
                while t < effective_end and len(timestamps) < max_frames:
                    timestamps.append(t)
                    t += interval
                if not timestamps:
                    raise RuntimeError("抽帧时间范围为空")

                saved: list[str] = []
                failed_ts: list[float] = []  # 记录失败的时间戳用于诊断
                for i, ts in enumerate(timestamps):
                    out = os.path.join(tmp_dir, f"frame_{i:04d}.png")
                    # 策略1: 输入定位（快速，依赖关键帧索引）
                    proc = subprocess.run(
                        [ffmpeg, "-y", "-ss", str(ts), "-i", video_path,
                         "-vframes", "1", "-f", "image2", "-q:v", "2", out],
                        capture_output=True,
                    )
                    ok = proc.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0
                    if not ok:
                        # 策略2: 输出定位重试（慢但更可靠，逐帧精确解码定位）
                        if os.path.exists(out):
                            os.unlink(out)
                        proc = subprocess.run(
                            [ffmpeg, "-y", "-i", video_path,
                             "-ss", str(ts), "-vframes", "1",
                             "-f", "image2", "-q:v", "2", out],
                            capture_output=True,
                        )
                        ok = proc.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0
                        if not ok:
                            failed_ts.append(ts)
                            print(f"[VF] 帧 {i} 取帧失败 (t={ts:.2f}s): "
                                  f"stderr={proc.stderr.decode(errors='ignore')[:200]}")
                            if os.path.exists(out):
                                os.unlink(out)
                            continue
                    saved.append(out)
                    _jobs[job_id]["progress"] = int((i + 1) / len(timestamps) * 80)

                if failed_ts:
                    print(f"[VF] {job_id}: {len(failed_ts)}/{len(timestamps)} 帧取帧失败, "
                          f"时间戳: {[f'{t:.2f}' for t in failed_ts]}")

                if not saved:
                    raise RuntimeError("ffmpeg 未生成任何帧")
                timestamps = timestamps[:len(saved)]
            else:
                output_pattern = os.path.join(tmp_dir, "frame_%04d.png")
                proc = subprocess.run(
                    [ffmpeg, "-i", video_path, "-vf", f"fps={fps}",
                     "-vframes", str(max_frames), "-q:v", "2", "-y", output_pattern],
                    capture_output=True,
                )
                if proc.returncode != 0:
                    raise RuntimeError(f"ffmpeg 抽帧失败: {proc.stderr.decode(errors='ignore')[:300]}")
                frame_files = sorted(
                    f for f in os.listdir(tmp_dir)
                    if f.startswith("frame_") and f.endswith(".png")
                )
                saved = [os.path.join(tmp_dir, fname) for fname in frame_files[:max_frames]]
                timestamps = [float(i) / fps for i in range(len(saved))]

            _jobs[job_id]["progress"] = 80

            # 获取帧尺寸（先取第一帧看原始大小）
            first_img = PILImage.open(saved[0])
            orig_w, orig_h = first_img.size
            first_img.close()

            # 计算裁剪框
            print(f"[VF-CROP] {job_id}: left={crop_left} right={crop_right} top={crop_top} bottom={crop_bottom} orig={orig_w}x{orig_h}")
            has_crop = crop_left > 0 or crop_right > 0 or crop_top > 0 or crop_bottom > 0
            if has_crop:
                crop_box = (
                    max(0, crop_left),
                    max(0, crop_top),
                    max(1, orig_w - crop_right),
                    max(1, orig_h - crop_bottom),
                )
                fw = crop_box[2] - crop_box[0]
                fh = crop_box[3] - crop_box[1]
                if fw <= 0 or fh <= 0:
                    fw, fh = orig_w, orig_h
                    has_crop = False
            else:
                fw, fh = orig_w, orig_h

            # 复制帧到任务目录（如需裁剪则先裁剪）
            frame_dir = jd / "frames"
            frame_dir.mkdir(exist_ok=True)
            for i, sp in enumerate(saved):
                dst = frame_dir / f"frame_{i:04d}.png"
                if has_crop:
                    img = PILImage.open(sp)
                    cropped = img.crop(crop_box)
                    cropped.save(dst, "PNG")
                    if i == 0:
                        print(f"[VF-CROP] {job_id}: applied crop {crop_box} -> {cropped.size}")
                    cropped.close()
                    img.close()
                else:
                    shutil.copy2(sp, dst)

            # 收集裁剪后的帧路径（用于合成）
            frame_paths = sorted(
                str(frame_dir / fname)
                for fname in os.listdir(str(frame_dir))
                if fname.endswith(".png")
            )

            # 合成 Sprite Sheet
            sheet_path = str(jd / "sprite.png")
            index_data = compose_sprite_sheet(
                frame_paths=frame_paths,
                timestamps=timestamps,
                frame_w=fw,
                frame_h=fh,
                spacing=spacing,
                layout_mode=layout_mode,
                columns=columns,
                output_path=sheet_path,
            )

            # 保存索引 JSON
            index_path = jd / "index.json"
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

            _jobs[job_id].update(
                status="completed",
                progress=100,
                result={
                    "sprite_path": str(sheet_path),
                    "index_path": str(index_path),
                    "frame_count": len(saved),
                    "frame_size": {"w": fw, "h": fh},
                    "sheet_size": index_data["sheet_size"],
                },
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    except Exception as e:
        _jobs[job_id].update(status="failed", error={"message": str(e)})


@router.post("/video-frames/jobs")
async def create_job(
    file: UploadFile = File(...),
    fps: int = Form(default=8),
    max_frames: int = Form(default=16),
    start_sec: float = Form(default=0.0),
    end_sec: float = Form(default=0.0),
    spacing: int = Form(default=4),
    layout_mode: str = Form(default="auto_square"),
    columns: int = Form(default=8),
    crop_left: int = Form(default=0),
    crop_right: int = Form(default=0),
    crop_top: int = Form(default=0),
    crop_bottom: int = Form(default=0),
):
    """上传视频并创建抽帧任务"""
    job_id = uuid.uuid4().hex[:12]

    if not file.filename:
        raise HTTPException(400, "请上传视频文件")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(400, f"不支持的格式: {ext}")

    content = await file.read()
    if len(content) > MAX_VIDEO_MB * 1024 * 1024:
        raise HTTPException(400, f"文件过大，限制 {MAX_VIDEO_MB}MB")

    jd = _job_dir(job_id)
    video_path = jd / "input_video.mp4"
    with open(video_path, "wb") as f:
        f.write(content)

    params = {
        "fps": fps, "max_frames": max_frames,
        "start_sec": start_sec, "end_sec": end_sec,
        "spacing": spacing, "layout_mode": layout_mode, "columns": columns,
        "crop_left": crop_left, "crop_right": crop_right,
        "crop_top": crop_top, "crop_bottom": crop_bottom,
    }

    _jobs[job_id] = {
        "id": job_id,
        "status": "processing",
        "progress": 0,
        "params": params,
        "result": None,
        "error": None,
    }

    t = threading.Thread(target=_run_extraction_sync, args=(job_id, str(video_path), params))
    t.daemon = True
    t.start()

    return {"job_id": job_id, "status": "processing"}


@router.get("/video-frames/jobs/{job_id}")
async def get_job(job_id: str):
    """查询抽帧任务状态"""
    if job_id not in _jobs:
        raise HTTPException(404, "任务不存在")
    j = _jobs[job_id]
    return {
        "id": job_id,
        "status": j["status"],
        "progress": j.get("progress", 0),
        "params": j.get("params"),
        "error": j.get("error"),
        "result": j.get("result"),
    }


@router.get("/video-frames/jobs/{job_id}/result")
async def get_result(job_id: str, format: str = "png"):
    """下载结果（sprite.png 或 zip 包）"""
    if job_id not in _jobs:
        raise HTTPException(404, "任务不存在")
    if _jobs[job_id]["status"] != "completed":
        raise HTTPException(400, "任务未完成")

    jd = _job_dir(job_id)
    sprite = jd / "sprite.png"
    index_json = jd / "index.json"

    if not sprite.exists():
        raise HTTPException(404, "结果文件不存在")

    if format == "zip":
        import zipfile
        zip_path = jd / "result.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(sprite, "sprite.png")
            if index_json.exists():
                zf.write(index_json, "index.json")
        return FileResponse(zip_path, filename="sprite_sheet.zip", media_type="application/zip")

    return FileResponse(sprite, filename="sprite.png", media_type="image/png")


@router.get("/video-frames/jobs/{job_id}/index")
async def get_index(job_id: str):
    """获取索引 JSON"""
    jd = _job_dir(job_id)
    index_path = jd / "index.json"
    if not index_path.exists():
        raise HTTPException(404, "索引文件不存在")
    return FileResponse(index_path, media_type="application/json")


@router.delete("/video-frames/jobs/{job_id}")
async def delete_job(job_id: str):
    """删除任务及文件"""
    if job_id in _jobs:
        del _jobs[job_id]
    jd = _job_dir(job_id)
    if jd.exists():
        shutil.rmtree(jd, ignore_errors=True)
    return {"ok": True}


# ============ 帧文件列表 ============

@router.get("/video-frames/jobs/{job_id}/frames")
async def get_job_frames(job_id: str):
    """返回抽帧任务的单帧图片文件列表（base64 缩略图或路径）"""
    if job_id not in _jobs:
        raise HTTPException(404, "任务不存在")
    jd = _job_dir(job_id)
    frame_dir = jd / "frames"
    if not frame_dir.exists():
        # 如果 frames 目录不存在，返回空列表
        return {"frames": [], "frame_count": 0}

    frame_files = sorted(
        f.name for f in frame_dir.iterdir()
        if f.suffix.lower() in ALLOWED_IMAGE_EXT
    )
    return {
        "frames": [
            {
                "name": fname,
                "url": f"/api/video-frames/jobs/{job_id}/frames/{fname}",
            }
            for fname in frame_files
        ],
        "frame_count": len(frame_files),
    }


@router.get("/video-frames/jobs/{job_id}/frames/{filename}")
async def get_frame_file(job_id: str, filename: str):
    """获取单帧图片文件"""
    if job_id not in _jobs:
        raise HTTPException(404, "任务不存在")
    jd = _job_dir(job_id)
    fp = jd / "frames" / filename
    if not fp.exists():
        raise HTTPException(404, "帧文件不存在")
    return FileResponse(fp, media_type="image/png")


# ============ 裁剪帧 ============

@router.post("/video-frames/jobs/{job_id}/crop")
async def crop_frames(
    job_id: str,
    left: int = 0,
    top: int = 0,
    right: int = 0,
    bottom: int = 0,
):
    """裁剪所有帧并重新合成精灵表"""
    if job_id not in _jobs:
        raise HTTPException(404, "任务不存在")
    if _jobs[job_id]["status"] != "completed":
        raise HTTPException(400, "任务未完成")

    try:
        jd = _job_dir(job_id)
        frame_dir = jd / "frames"
        if not frame_dir.exists():
            raise HTTPException(400, "帧目录不存在")

        frame_files = sorted(
            f for f in frame_dir.iterdir()
            if f.suffix.lower() in ALLOWED_IMAGE_EXT
        )
        if not frame_files:
            raise HTTPException(400, "没有可裁剪的帧")

        # 读取第一帧获取原始尺寸
        first_img = PILImage.open(frame_files[0])
        orig_w, orig_h = first_img.size
        first_img.close()

        # 校验裁剪参数
        crop_left = max(0, min(left, orig_w - 1))
        crop_top = max(0, min(top, orig_h - 1))
        crop_right = max(0, min(right, orig_w - crop_left - 1))
        crop_bottom = max(0, min(bottom, orig_h - crop_top - 1))

        crop_box = (crop_left, crop_top, orig_w - crop_right, orig_h - crop_bottom)
        new_w = orig_w - crop_left - crop_right
        new_h = orig_h - crop_top - crop_bottom

        if new_w <= 0 or new_h <= 0:
            raise HTTPException(400, "裁剪区域无效，请减小裁切值")

        # 裁剪所有帧
        cropped_dir = jd / "cropped"
        cropped_dir.mkdir(exist_ok=True)
        cropped_paths = []
        for fp in frame_files:
            img = PILImage.open(fp)
            cropped = img.crop(crop_box)
            out_name = fp.name
            out_path = cropped_dir / out_name
            cropped.save(out_path, "PNG")
            cropped.close()
            img.close()
            cropped_paths.append(str(out_path))

        # 重新合成精灵表
        params = _jobs[job_id].get("params", {})
        spacing = params.get("spacing", 4)
        layout_mode = params.get("layout_mode", "auto_square")
        columns = params.get("columns", 8)

        # 从索引中获取时间戳
        timestamps: list[float] = []
        index_path = jd / "index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                idx = json.load(f)
                timestamps = [fr["t"] for fr in idx.get("frames", [])]
        if not timestamps or len(timestamps) != len(cropped_paths):
            timestamps = [float(i) for i in range(len(cropped_paths))]

        sheet_path = str(jd / "sprite.png")
        index_data = compose_sprite_sheet(
            frame_paths=cropped_paths,
            timestamps=timestamps,
            frame_w=new_w,
            frame_h=new_h,
            spacing=spacing,
            layout_mode=layout_mode,
            columns=columns,
            output_path=sheet_path,
        )

        # 保存新索引
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

        # 更新结果
        _jobs[job_id]["result"] = {
            "sprite_path": str(sheet_path),
            "index_path": str(index_path),
            "frame_count": len(cropped_paths),
            "frame_size": {"w": new_w, "h": new_h},
            "sheet_size": index_data["sheet_size"],
            "crop": {"left": crop_left, "top": crop_top, "right": crop_right, "bottom": crop_bottom},
        }

        return {
            "status": "ok",
            "frame_size": {"w": new_w, "h": new_h},
            "sheet_size": index_data["sheet_size"],
            "frame_count": len(cropped_paths),
            "crop": {"left": crop_left, "top": crop_top, "right": crop_right, "bottom": crop_bottom},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"裁剪失败: {str(e)}")


# ============ 保存处理后的帧 ============

from pydantic import BaseModel


class SaveFramesRequest(BaseModel):
    """保存帧请求：接收前端处理后的帧数据"""
    frames: list[str]  # base64 PNG 数据列表


class ComposeRequest(BaseModel):
    """重新合成请求"""
    columns: int = 8
    margin: int = 0
    spacing: int = 4
    cell_size: int = 0
    smooth: bool = False


@router.post("/video-frames/jobs/{job_id}/save-frames")
async def save_frames(job_id: str, req: SaveFramesRequest):
    """接收前端处理后的帧数据，覆写帧目录并更新索引"""
    if job_id not in _jobs:
        raise HTTPException(404, "任务不存在")
    if _jobs[job_id]["status"] != "completed":
        raise HTTPException(400, "任务未完成")

    try:
        import base64

        jd = _job_dir(job_id)
        frame_dir = jd / "frames"
        frame_dir.mkdir(exist_ok=True)

        # 清空旧帧
        for f in frame_dir.iterdir():
            if f.suffix.lower() in ALLOWED_IMAGE_EXT:
                f.unlink()

        # 写入新帧
        saved_count = 0
        fw, fh = None, None
        for i, b64_data in enumerate(req.frames):
            if not b64_data:
                continue
            # 支持带或不带 data:image/png;base64, 前缀
            if "," in b64_data and b64_data.startswith("data:"):
                b64_data = b64_data.split(",", 1)[1]
            try:
                img_bytes = base64.b64decode(b64_data)
            except Exception:
                continue
            dst = frame_dir / f"frame_{i:04d}.png"
            dst.write_bytes(img_bytes)
            if fw is None:
                try:
                    with PILImage.open(dst) as test_img:
                        fw, fh = test_img.size
                except Exception:
                    pass
            saved_count += 1

        if saved_count == 0:
            raise HTTPException(400, "没有有效的帧数据")

        # 更新帧尺寸到 result
        if fw is not None and fh is not None:
            result = _jobs[job_id].get("result") or {}
            result["frame_size"] = {"w": fw, "h": fh}
            _jobs[job_id]["result"] = result

        return {
            "status": "ok",
            "saved": saved_count,
            "frame_size": {"w": fw, "h": fh} if fw else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"保存帧失败: {str(e)}")


@router.post("/video-frames/jobs/{job_id}/compose")
async def compose_sprite(job_id: str, req: ComposeRequest):
    """用当前帧目录重新合成精灵表（支持边距/间距/单帧尺寸参数）"""
    if job_id not in _jobs:
        raise HTTPException(404, "任务不存在")
    if _jobs[job_id]["status"] != "completed":
        raise HTTPException(400, "任务未完成")

    try:
        import math

        jd = _job_dir(job_id)
        frame_dir = jd / "frames"
        if not frame_dir.exists():
            raise HTTPException(400, "帧目录不存在")

        frame_files = sorted(
            str(fp) for fp in frame_dir.iterdir()
            if fp.suffix.lower() in ALLOWED_IMAGE_EXT
        )
        if not frame_files:
            raise HTTPException(400, "没有可合成的帧")

        # 读取第一帧获取原始尺寸
        first_img = PILImage.open(frame_files[0])
        orig_w, orig_h = first_img.size
        first_img.close()

        # 获取时间戳
        timestamps: list[float] = []
        index_path = jd / "index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                idx = json.load(f)
                timestamps = [fr["t"] for fr in idx.get("frames", [])]
        if not timestamps or len(timestamps) != len(frame_files):
            timestamps = [float(i) for i in range(len(frame_files))]

        columns = max(1, req.columns)
        margin = max(0, req.margin)
        spacing = max(0, req.spacing)
        cell_size = max(0, req.cell_size)

        # 帧尺寸处理
        if cell_size > 0:
            # 缩放到统一尺寸
            processed_frames = []
            for fp in frame_files:
                img = PILImage.open(fp)
                if img.size != (cell_size, cell_size):
                    if req.smooth:
                        img = img.resize((cell_size, cell_size), PILImage.Resampling.LANCZOS)
                    else:
                        img = img.resize((cell_size, cell_size), PILImage.Resampling.NEAREST)
                processed_frames.append(img)
            fw = fh = cell_size
            use_processed = True
        else:
            use_processed = False
            fw, fh = orig_w, orig_h

        # 计算布局
        n = len(frame_files)
        cols = min(columns, n)
        rows = math.ceil(n / cols)

        cell_total_w = fw + 2 * margin
        cell_total_h = fh + 2 * margin
        sheet_w = cols * cell_total_w + (cols - 1) * spacing
        sheet_h = rows * cell_total_h + (rows - 1) * spacing

        # 合成大图
        sheet = PILImage.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
        for i in range(n):
            col = i % cols
            row = i // cols
            x = col * (cell_total_w + spacing) + margin
            y = row * (cell_total_h + spacing) + margin
            if use_processed:
                sheet.paste(processed_frames[i], (x, y))
            else:
                img = PILImage.open(frame_files[i])
                sheet.paste(img, (x, y))
                img.close()

        # 保存
        sheet_path = str(jd / "sprite.png")
        sheet.save(sheet_path, "PNG")
        sheet.close()
        if use_processed:
            for img in processed_frames:
                img.close()

        # 更新索引
        index_data = {
            "version": "1.0",
            "frame_size": {"w": fw, "h": fh},
            "sheet_size": {"w": sheet_w, "h": sheet_h},
            "frames": [
                {
                    "i": i,
                    "x": (i % cols) * (cell_total_w + spacing) + margin,
                    "y": (i // cols) * (cell_total_h + spacing) + margin,
                    "w": fw,
                    "h": fh,
                    "t": timestamps[i] if i < len(timestamps) else float(i),
                }
                for i in range(n)
            ],
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

        # 更新 result
        _jobs[job_id]["result"] = {
            "sprite_path": str(sheet_path),
            "index_path": str(index_path),
            "frame_count": n,
            "frame_size": {"w": fw, "h": fh},
            "sheet_size": {"w": sheet_w, "h": sheet_h},
        }

        return {
            "status": "ok",
            "frame_count": n,
            "frame_size": {"w": fw, "h": fh},
            "sheet_size": {"w": sheet_w, "h": sheet_h},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"合成失败: {str(e)}")


# ============ AI 抠图 ============

@router.post("/video-frames/matte")
async def matte_image(
    file: UploadFile = File(...),
    model: str = Form("isnet-general-use"),
    alpha_matting: bool = Form(False),
):
    """AI 抠图：上传单张图片返回透明 PNG

    统一通过 CapabilityRouter → RembgProvider 执行。
    支持通过 model 参数指定 rembg session 模型（默认 isnet-general-use）。
    alpha_matting=True 时启用边缘精细修边处理。
    """
    if not file.filename:
        raise HTTPException(400, "请上传图片文件")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"不支持的格式: {ext}")

    content = await file.read()
    if len(content) > MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(400, f"图片不得超过 {MAX_IMAGE_MB}MB")

    try:
        import io

        image = PILImage.open(io.BytesIO(content)).convert("RGBA")

        from .deps import get_router
        from ..providers.base import Capability

        router = get_router()
        result = await router.route(
            Capability.REMOVE_BG,
            {"image": image, "session": model, "alpha_matting": alpha_matting},
        )

        output_image = result["image"]
        buf = io.BytesIO()
        output_image.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(500, f"抠图失败: {str(e)}")


# ============ 水印去除 ============

def _run_watermark_sync(job_id: str, video_path: str):
    """后台线程：水印去除"""
    try:
        from ..tools.watermark_remover import run_watermark_pipeline
        result = run_watermark_pipeline(job_id, video_path, str(_DATA_DIR))
        _wm_jobs[job_id].update(status="completed", progress=100, result=result)
    except Exception as e:
        _wm_jobs[job_id].update(status="failed", error={"message": str(e)})


@router.post("/video-frames/watermark")
async def create_watermark_job(file: UploadFile = File(...)):
    """创建水印去除任务"""
    job_id = uuid.uuid4().hex[:12]

    if not file.filename:
        raise HTTPException(400, "请上传视频文件")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(400, f"不支持的格式: {ext}")

    content = await file.read()
    if len(content) > MAX_VIDEO_MB * 1024 * 1024:
        raise HTTPException(400, f"文件过大，限制 {MAX_VIDEO_MB}MB")

    jd = _job_dir(job_id)
    video_path = jd / "input_video.mp4"
    with open(video_path, "wb") as f:
        f.write(content)

    _wm_jobs[job_id] = {
        "id": job_id,
        "status": "processing",
        "progress": 0,
        "result": None,
        "error": None,
    }

    t = threading.Thread(target=_run_watermark_sync, args=(job_id, str(video_path)))
    t.daemon = True
    t.start()

    return {"job_id": job_id, "status": "processing"}


@router.get("/video-frames/watermark/{job_id}")
async def get_watermark_job(job_id: str):
    """查询水印任务状态"""
    if job_id not in _wm_jobs:
        raise HTTPException(404, "任务不存在")
    j = _wm_jobs[job_id]
    return {
        "id": job_id,
        "status": j["status"],
        "progress": j.get("progress", 0),
        "error": j.get("error"),
        "result": j.get("result"),
    }


@router.get("/video-frames/watermark/{job_id}/result")
async def get_watermark_result(job_id: str):
    """下载去水印视频"""
    if job_id not in _wm_jobs:
        raise HTTPException(404, "任务不存在")
    if _wm_jobs[job_id]["status"] != "completed":
        raise HTTPException(400, "任务未完成")

    j = _wm_jobs[job_id]
    out = j.get("result", {}).get("output", "")
    p = Path(out)
    if not p.exists():
        p = _DATA_DIR / job_id / "clean.mp4"
    if not p.exists():
        raise HTTPException(404, "结果文件不存在")

    return FileResponse(p, filename="clean.mp4", media_type="video/mp4")


@router.delete("/video-frames/watermark/{job_id}")
async def delete_watermark_job(job_id: str):
    """删除水印任务"""
    if job_id in _wm_jobs:
        del _wm_jobs[job_id]
    jd = _job_dir(job_id)
    if jd.exists():
        shutil.rmtree(jd, ignore_errors=True)
    return {"ok": True}
