"""
Model Settings Router — 模型配置管理 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..services.model_settings_service import (
    get_all_settings,
    update_provider_settings,
    create_provider_settings,
    delete_provider_settings,
    init_default_settings,
    get_model_visibility,
    update_model_visibility,
    update_category_visibility,
    create_custom_node,
    update_custom_node,
    delete_custom_node,
    soft_delete_model,
    restore_model,
    get_deleted_models,
)

router = APIRouter()


@router.get("/settings")
async def get_model_settings(db: AsyncSession = Depends(get_db)):
    """获取所有 AI 提供商的当前配置"""
    try:
        return await get_all_settings(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/{provider}")
async def update_model_settings(provider: str, data: dict, db: AsyncSession = Depends(get_db)):
    """更新指定 AI 提供商的配置"""
    try:
        return await update_provider_settings(db, provider, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/init")
async def initialize_settings(db: AsyncSession = Depends(get_db)):
    """初始化默认配置（从 .env 同步到 DB）"""
    try:
        await init_default_settings(db)
        return {"status": "initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings")
async def create_model_settings(data: dict, db: AsyncSession = Depends(get_db)):
    """创建新的 AI 提供商"""
    try:
        return await create_provider_settings(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/settings/{provider}")
async def delete_model_settings(provider: str, db: AsyncSession = Depends(get_db)):
    """删除一个 AI 提供商"""
    try:
        return await delete_provider_settings(db, provider)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 节点类型可见性管理 ==========

@router.get("/nodes")
async def get_nodes_visibility(db: AsyncSession = Depends(get_db)):
    """获取所有节点类型的可见性状态"""
    try:
        return await get_model_visibility(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/nodes/{model_id}")
async def update_node_visibility(model_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    """更新单个节点类型的显示/隐藏状态"""
    try:
        is_visible = data.get("is_visible", True)
        return await update_model_visibility(db, model_id, is_visible)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/nodes/category/{category}")
async def update_category_nodes_visibility(category: str, data: dict, db: AsyncSession = Depends(get_db)):
    """批量更新一个分类下所有节点类型的显示/隐藏状态"""
    try:
        is_visible = data.get("is_visible", True)
        return await update_category_visibility(db, category, is_visible)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 自定义节点 CRUD ==========

@router.post("/nodes", status_code=201)
async def create_node(data: dict, db: AsyncSession = Depends(get_db)):
    """创建自定义节点类型"""
    try:
        return await create_custom_node(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/nodes/{model_id}/schema")
async def update_node_schema(model_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    """更新自定义节点 Schema"""
    try:
        return await update_custom_node(db, model_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/nodes/{model_id}")
async def delete_node(model_id: str, db: AsyncSession = Depends(get_db)):
    """删除模型（统一软删除，不物理删除）"""
    try:
        return await soft_delete_model(db, model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 内置模型 软删除 / 恢复 ==========

@router.put("/nodes/{model_id}/soft-delete")
async def soft_delete_node(model_id: str, db: AsyncSession = Depends(get_db)):
    """软删除一个模型（内置模型标记删除，自定义模型物理删除）"""
    try:
        return await soft_delete_model(db, model_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/nodes/{model_id}/restore")
async def restore_node(model_id: str, db: AsyncSession = Depends(get_db)):
    """恢复一个已软删除的模型"""
    try:
        return await restore_model(db, model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nodes/deleted")
async def list_deleted_models(db: AsyncSession = Depends(get_db)):
    """获取所有已软删除的模型"""
    try:
        return await get_deleted_models(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
