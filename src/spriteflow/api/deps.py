"""依赖注入 — 存放全局单例的获取函数，避免循环导入"""

from __future__ import annotations

from typing import Any

from ..asset_hub.db import AssetDB
from ..storage.base import StorageBackend
from ..providers.router import CapabilityRouter
from ..engine.executor import Executor

# ---- 全局单例（由 app.py lifespan 初始化） ----

_db: AssetDB | None = None
_storage: StorageBackend | None = None
_router: CapabilityRouter | None = None
_executor: Executor | None = None


def get_db() -> AssetDB:
    assert _db is not None, "数据库未初始化"
    return _db


def get_storage() -> StorageBackend:
    assert _storage is not None, "存储后端未初始化"
    return _storage


def get_router() -> CapabilityRouter:
    assert _router is not None, "路由器未初始化"
    return _router


def get_executor() -> Executor:
    assert _executor is not None, "执行器未初始化"
    return _executor


def set_db(db: AssetDB) -> None:
    global _db
    _db = db


def set_storage(storage: StorageBackend) -> None:
    global _storage
    _storage = storage


def set_router(router: CapabilityRouter) -> None:
    global _router
    _router = router


def set_executor(executor: Executor) -> None:
    global _executor
    _executor = executor
