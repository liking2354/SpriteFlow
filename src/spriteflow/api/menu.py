"""菜单配置 API — 读写侧栏菜单可见性与排序（持久化到 configs 表）

当前单用户模式：数据存储在 configs 表 key="menu:items"
未来多用户/权限场景：可扩展为独立 menu_configs 表，增加 user_id 列
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from .deps import get_db

router = APIRouter()

MENU_KEY = "menu:items"


@router.get("/menu")
async def get_menu():
    """获取菜单配置"""
    db = get_db()
    raw = await db.get_config(MENU_KEY)
    if raw is None:
        return {"items": None}  # 前端使用默认值
    try:
        items = json.loads(raw)
        return {"items": items}
    except json.JSONDecodeError:
        return {"items": None}


@router.put("/menu")
async def update_menu(payload: dict):
    """更新菜单配置

    payload: { "items": [...] }
    """
    db = get_db()
    items = payload.get("items")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items 字段必须为数组")
    await db.set_config(MENU_KEY, json.dumps(items, ensure_ascii=False))
    return {"status": "ok", "count": len(items)}
