"""
App Router — 文件上传等应用级端点
"""
import os
import shutil
from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from ..workflow_helper import get_file_upload_url_helper
from ...config import settings

router = APIRouter()


class DynamicCostRequest(BaseModel):
    task_name: str
    payload: dict = {}


@router.post("/calculate_dynamic_cost")
async def calculate_dynamic_cost(req: DynamicCostRequest):
    """计算动态成本 — 当前为占位实现，返回 0"""
    return {"cost": 0}


@router.get("/get_file_upload_url")
async def get_file_upload_url(request: Request):
    """获取文件上传预签名 URL — 本地版返回本地存储端点"""
    try:
        params = dict(request.query_params)
        return await get_file_upload_url_helper(params)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload/{filename}")
async def upload_file(filename: str, file: UploadFile = File(...)):
    """上传文件到本地存储"""
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)

    # 安全检查：防止路径穿越
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(upload_dir, safe_filename)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    file_url = f"{settings.static_url_prefix}/{safe_filename}"
    return {
        "filename": safe_filename,
        "url": file_url,
        "size": os.path.getsize(file_path),
        "content_type": file.content_type,
    }
