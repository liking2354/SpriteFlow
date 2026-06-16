"""费用计算 API — 根据模型类型、尺寸、分辨率计算 token 消耗

POST /api/calculate_cost

请求参数：
  - model_type: text2img | text2video | img2video
  - sub_model: standard | express | sora2
  - width: int    (图片宽度，仅 text2img)
  - height: int   (图片高度，仅 text2img)
  - resolution: 480p | 720p    (视频分辨率)
  - duration: int              (视频时长，秒，默认 5)

返回：
  - token_usage: float     本次生成消耗的 token
  - daily_credit: float    每日信用额度
  - remaining_calls: int   剩余可调用次数
  - breakdown: dict        费用明细
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

# ==================== 定价常量 ====================

# 图片模型倍率
IMAGE_MODEL_MULTIPLIER = {
    "standard": 1,
    "express": 2,
    "sora2": 10,
}

# 图片尺寸换算系数：credits = (width * height) / PIXEL_PER_CREDIT
PIXEL_PER_CREDIT = 3_300_000  # ~0.1 积分 / 0.33MP

# 视频基础率（积分/秒）
VIDEO_BASE_RATE_PER_SEC = 0.1

# 视频分辨率费率（积分/秒）
VIDEO_RESOLUTION_RATE = {
    "480p": 0.5,
    "720p": 1.0,
}

# 视频默认时长（秒）
VIDEO_DEFAULT_DURATION = 5

# 每日信用额度
DAILY_CREDIT = 300.0


# ==================== 请求/响应模型 ====================

class CostCalcRequest(BaseModel):
    model_type: str = Field(..., description="text2img | text2video | img2video")
    sub_model: str = Field("standard", description="standard | express | sora2")
    width: int | None = Field(None, ge=1, description="图片宽度（仅 text2img）")
    height: int | None = Field(None, ge=1, description="图片高度（仅 text2img）")
    resolution: str | None = Field(None, description="视频分辨率：480p | 720p")
    duration: int = Field(VIDEO_DEFAULT_DURATION, ge=1, le=30, description="视频时长（秒）")


class CostBreakdown(BaseModel):
    dimension_pixels: int | None = None
    dimension_credits: float = 0.0
    model_multiplier: int = 1
    model_credits: float = 0.0
    resolution_credits: float = 0.0
    duration_seconds: int = 0
    total: float = 0.0


class CostCalcResponse(BaseModel):
    token_usage: float
    daily_credit: float = DAILY_CREDIT
    remaining_calls: int
    breakdown: CostBreakdown


# ==================== 路由 ====================

@router.post("/api/calculate_cost", response_model=CostCalcResponse, tags=["cost"])
async def calculate_cost(req: CostCalcRequest):
    """计算单次生成的 token 消耗和剩余可调用次数"""
    breakdown = CostBreakdown()

    if req.model_type == "text2img":
        if not req.width or not req.height:
            from fastapi import HTTPException
            raise HTTPException(400, "text2img 必须提供 width 和 height")

        pixels = req.width * req.height
        multiplier = IMAGE_MODEL_MULTIPLIER.get(req.sub_model, 1)
        dimension_credits = pixels / PIXEL_PER_CREDIT

        token_usage = round(dimension_credits * multiplier, 2)

        breakdown = CostBreakdown(
            dimension_pixels=pixels,
            dimension_credits=round(dimension_credits, 4),
            model_multiplier=multiplier,
            model_credits=round(dimension_credits * multiplier, 2),
            total=token_usage,
        )

    elif req.model_type in ("text2video", "img2video"):
        resolution = req.resolution or "720p"
        duration = req.duration or VIDEO_DEFAULT_DURATION

        base_per_sec = VIDEO_BASE_RATE_PER_SEC
        resolution_per_sec = VIDEO_RESOLUTION_RATE.get(resolution, 1.0)

        token_usage = round((base_per_sec + resolution_per_sec) * duration, 2)

        breakdown = CostBreakdown(
            resolution_credits=round(resolution_per_sec * duration, 2),
            duration_seconds=duration,
            model_credits=round(base_per_sec * duration, 2),
            total=token_usage,
        )

    else:
        from fastapi import HTTPException
        raise HTTPException(400, f"不支持的 model_type: {req.model_type}")

    # 剩余调用次数（向下取整）
    remaining_calls = max(0, int(DAILY_CREDIT / token_usage)) if token_usage > 0 else 0

    return CostCalcResponse(
        token_usage=token_usage,
        daily_credit=DAILY_CREDIT,
        remaining_calls=remaining_calls,
        breakdown=breakdown,
    )
