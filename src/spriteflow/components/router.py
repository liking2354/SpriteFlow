"""
组件管理 & 测试 API

提供:
- GET  /api/components/list          列出所有已注册组件
- GET  /api/components/{id}          获取单个组件详情
- POST /api/components/{id}/test     独立测试组件（不依赖 workflow）
- POST /api/components/{id}/validate 仅校验输入参数
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .registry import ComponentRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/components", tags=["components"])


# ============================ Request/Response Models ============================


class ComponentInfo(BaseModel):
    component_id: str
    display_name: str
    category: str
    subcategory: str
    description: str
    version: str
    output_type: str
    model_config = {"extra": "allow"}


class TestRequest(BaseModel):
    """组件测试请求"""
    inputs: dict[str, Any] = {}
    params: dict[str, Any] = {}
    credentials: dict[str, Any] | None = None


class TestResponse(BaseModel):
    """组件测试响应"""
    success: bool
    component_id: str
    outputs: list[dict[str, Any]] | None = None
    error: str | None = None
    model_config = {"extra": "allow"}


class ValidateRequest(BaseModel):
    """校验请求"""
    inputs: dict[str, Any] = {}
    params: dict[str, Any] = {}


class ValidateResponse(BaseModel):
    """校验响应"""
    valid: bool
    errors: list[str] = []


# ============================ Endpoints ============================


@router.get("/list")
async def list_components():
    """列出所有已注册的组件"""
    metas = ComponentRegistry.list_all()
    result = []
    for cid, meta in metas.items():
        result.append({
            "component_id": cid,
            "display_name": meta.display_name,
            "category": meta.category,
            "subcategory": meta.subcategory,
            "description": meta.description,
            "version": meta.version,
            "output_type": meta.output_type,
            "credential_schema": meta.credential_schema,
            "input_schema": meta.input_schema,
            "input_required": meta.input_required,
        })
    return {"components": result, "total": len(result)}


@router.get("/{component_id}")
async def get_component(component_id: str):
    """获取单个组件详情"""
    meta = ComponentRegistry.get_meta(component_id)
    if not meta:
        raise HTTPException(404, f"组件 {component_id} 未注册")
    return {
        "component_id": component_id,
        "display_name": meta.display_name,
        "category": meta.category,
        "subcategory": meta.subcategory,
        "description": meta.description,
        "version": meta.version,
        "output_type": meta.output_type,
        "credential_schema": meta.credential_schema,
        "input_schema": meta.input_schema,
        "input_required": meta.input_required,
    }


@router.post("/{component_id}/test", response_model=TestResponse)
async def test_component(component_id: str, req: TestRequest):
    """独立测试组件（不依赖 workflow 流程）

    直接调用组件的 execute() 方法，返回结果或错误。
    适用于开发调试和参数验证。
    """
    comp = ComponentRegistry.get(component_id)
    if not comp:
        raise HTTPException(404, f"组件 {component_id} 未注册")

    try:
        result = await comp.execute(
            inputs=req.inputs,
            params=req.params,
            credentials=req.credentials,
        )
        return TestResponse(
            success=True,
            component_id=component_id,
            outputs=result.get("outputs", []),
        )
    except Exception as e:
        logger.error(f"[ComponentTest] {component_id} failed: {e}")
        return TestResponse(
            success=False,
            component_id=component_id,
            error=str(e),
        )


@router.post("/{component_id}/validate", response_model=ValidateResponse)
async def validate_component(component_id: str, req: ValidateRequest):
    """校验组件输入参数"""
    comp = ComponentRegistry.get(component_id)
    if not comp:
        raise HTTPException(404, f"组件 {component_id} 未注册")

    try:
        errors = await comp.validate(inputs=req.inputs, params=req.params)
    except Exception as e:
        errors = [str(e)]

    return ValidateResponse(valid=len(errors) == 0, errors=errors)
