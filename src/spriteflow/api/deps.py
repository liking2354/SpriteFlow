"""依赖注入 — 存放全局单例的获取函数，避免循环导入"""

from __future__ import annotations

import sys as _sys
from typing import TYPE_CHECKING, Any

from ..asset_hub.db import AssetDB
from ..storage.base import StorageBackend
from ..providers.router import CapabilityRouter
from ..engine.executor import Executor

if TYPE_CHECKING:
    from ..templates.db import TemplateDB

# ---- 全局单例（由 app.py lifespan 初始化） ----

_db: AssetDB | None = None
_storage: StorageBackend | None = None
_router: CapabilityRouter | None = None
_executor: Executor | None = None
_template_db: TemplateDB | None = None  # noqa: F821 — TYPE_CHECKING only


def _get_peer_modules() -> list:
    """Find all deps module instances in sys.modules (handles dual-import scenarios).

    When uvicorn is started with ``src.spriteflow.api.app:app``, the relative
    import ``from .deps import ...`` in app.py resolves to ``src.spriteflow.api.deps``.
    But components that use ``from spriteflow.api.deps import ...`` touch a
    different module object where the globals were never initialised.

    This helper discovers all loaded copies of this module so setters can update
    every copy, guaranteeing that any import path always sees the same singleton.
    """
    peers = []
    for name in (
        "spriteflow.api.deps",
        "src.spriteflow.api.deps",
    ):
        mod = _sys.modules.get(name)
        if mod is not None:
            peers.append(mod)
    return peers


def get_db() -> AssetDB:
    global _db
    if _db is None:
        for peer in _get_peer_modules():
            if peer._db is not None:
                _db = peer._db
                break
    assert _db is not None, "数据库未初始化"
    return _db


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        for peer in _get_peer_modules():
            if peer._storage is not None:
                _storage = peer._storage
                break
    assert _storage is not None, "存储后端未初始化"
    return _storage


def get_router() -> CapabilityRouter:
    global _router
    if _router is None:
        for peer in _get_peer_modules():
            if peer._router is not None:
                _router = peer._router
                break
    assert _router is not None, "路由器未初始化"
    return _router


def get_executor() -> Executor:
    global _executor
    if _executor is None:
        for peer in _get_peer_modules():
            if peer._executor is not None:
                _executor = peer._executor
                break
    assert _executor is not None, "执行器未初始化"
    return _executor


def set_db(db: AssetDB) -> None:
    global _db
    _db = db
    for peer in _get_peer_modules():
        peer._db = db


def set_storage(storage: StorageBackend) -> None:
    global _storage
    _storage = storage
    for peer in _get_peer_modules():
        peer._storage = storage


def set_router(router: CapabilityRouter) -> None:
    global _router
    _router = router
    for peer in _get_peer_modules():
        peer._router = router


def set_executor(executor: Executor) -> None:
    global _executor
    _executor = executor
    for peer in _get_peer_modules():
        peer._executor = executor


def get_template_db() -> TemplateDB:
    assert _template_db is not None, "模板数据库未初始化"
    return _template_db


def set_template_db(db: TemplateDB) -> None:
    global _template_db
    _template_db = db
    for peer in _get_peer_modules():
        peer._template_db = db
