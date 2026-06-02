"""SpriteFlow CLI 入口"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .config import settings
from .engine.executor import Executor
from .engine.cache import CacheManager
from .workflow.yaml_loader import WorkflowLoader
from .storage.cos_storage import COSStorage
from .storage.local_storage import LocalStorage
from .asset_hub.db import AssetDB
from .providers.seedream import SeedreamProvider
from .providers.rembg_provider import RembgProvider
from .providers.router import CapabilityRouter

# 触发节点注册
from .nodes import *  # noqa: F401, F403


def main() -> None:
    parser = argparse.ArgumentParser(description="SpriteFlow — 2D 游戏素材生产工作流")
    subparsers = parser.add_subparsers(dest="command")

    # run 命令
    run_parser = subparsers.add_parser("run", help="执行工作流")
    run_parser.add_argument("workflow", help="YAML 工作流文件路径")

    # serve 命令
    serve_parser = subparsers.add_parser("serve", help="启动 API 服务")
    serve_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    serve_parser.add_argument("--port", type=int, default=8000, help="监听端口")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(_run_workflow(args.workflow))
    elif args.command == "serve":
        _serve(args.host, args.port)
    else:
        parser.print_help()


async def _run_workflow(yaml_path: str) -> None:
    """执行工作流"""
    from dotenv import load_dotenv
    load_dotenv()

    settings.ensure_dirs()

    # 初始化组件
    try:
        storage = COSStorage()
    except Exception:
        print("[WARN] COS 初始化失败，使用本地存储")
        storage = LocalStorage()

    db = AssetDB()
    await db.connect()
    await db.init_tables()

    router = CapabilityRouter()
    router.register_provider(
        SeedreamProvider(
            api_key=settings.ark_api_key,
            base_url=settings.ark_base_url,
            model=settings.seedream_model,
        )
    )
    router.register_provider(RembgProvider())
    router.set_credential("seedream", settings.ark_api_key)

    cache = CacheManager()
    executor = Executor(cache=cache, router=router, storage=storage)

    # 加载并验证工作流
    dag, name = WorkflowLoader.load(yaml_path)
    errors = WorkflowLoader.validate(dag)
    if errors:
        print(f"[ERROR] 工作流验证失败:")
        for e in errors:
            print(f"  - {e}")
        return

    print(f"[INFO] 执行工作流: {name}")
    print(f"[INFO] 节点数: {len(dag.nodes)}, 连线数: {len(dag.edges)}")

    # 执行
    run = await executor.execute(dag, workflow_name=name)

    # 打印结果
    print(f"\n[RESULT] 执行状态: {run.status.value}")
    for nid, result in run.results.items():
        cache_info = " (缓存命中)" if result.cache_hit else ""
        print(f"  节点 '{nid}': {result.status.value}{cache_info}")
        if result.error:
            print(f"    错误: {result.error}")

    await db.close()


def _serve(host: str, port: int) -> None:
    """启动 API 服务"""
    import uvicorn
    from .api.app import app
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
