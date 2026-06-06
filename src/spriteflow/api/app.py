"""FastAPI 应用工厂"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config import settings
from ..asset_hub.db import AssetDB
from ..asset_hub.ingest import IngestPipeline
from ..storage.cos_storage import COSStorage
from ..storage.local_storage import LocalStorage
from ..providers.seedream import SeedreamProvider
from ..providers.seedance import SeedanceProvider
from ..providers.rembg_provider import RembgProvider
from ..providers.volcengine_image import VolcengineImageProvider
from ..providers.openrouter import OpenRouterProvider
from ..providers.router import CapabilityRouter
from ..engine.cache import CacheManager
from ..engine.executor import Executor
from ..engine.video_worker import VideoWorker
from ..templates.db import TemplateDB
from ..templates.builder import PromptBuilder
from .deps import set_db, set_storage, set_router, set_executor, set_template_db

# 导入节点以触发注册
from ..nodes import *  # noqa: F401, F403

from .workflows import router as workflows_router
from .assets import router as assets_router
from .nodes import router as nodes_router
from .routing import router as routing_router
from .generate import router as generate_router
from .jobs import router as jobs_router
from .videos import router as videos_router
from ..templates.api import router as templates_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理"""
    settings.ensure_dirs()

    # 初始化数据库
    db = AssetDB()
    await db.connect()
    await db.init_tables()
    set_db(db)

    # 初始化存储
    try:
        storage = COSStorage()
        # 验证 COS 可用
        print(f"[SpriteFlow] COS 存储初始化成功: bucket={storage.bucket}, region={storage.region}")
    except Exception as e:
        print(f"[SpriteFlow] COS 初始化失败({e})，使用本地存储")
        storage = LocalStorage()
    set_storage(storage)

    # 初始化路由器
    router = CapabilityRouter()
    router.register_provider(
        SeedreamProvider(
            api_key=settings.ark_api_key,
            base_url=settings.ark_base_url,
            model=settings.seedream_model,
        )
    )
    seedance = SeedanceProvider(
        api_key=settings.ark_api_key,
        base_url=settings.ark_base_url,
        model=settings.seedance_model,
        timeout=settings.seedance_request_timeout,
    )
    router.register_provider(seedance)
    router.register_provider(RembgProvider())

    # 注册火山引擎图像处理 Provider
    volc_provider = VolcengineImageProvider(
        ak=settings.volc_access_key_id,
        sk=settings.volc_secret_access_key,
        mediakit_api_key=settings.volc_mediakit_api_key,
    )
    router.register_provider(volc_provider)
    router.set_credential("volcengine_image", settings.volc_access_key_id)
    # extra 中存 SK（Credential 只存 api_key 字段）
    # 通过 set_credential extra 方式存 SK 不方便，改为 provider 直接读 settings

    # 注册 OpenRouter Provider（多模型统一入口）
    openrouter = OpenRouterProvider(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.openrouter_default_model,
    )
    router.register_provider(openrouter)
    router.set_credential("openrouter", settings.openrouter_api_key)

    router.set_credential("seedream", settings.ark_api_key)
    router.set_credential("seedance", settings.ark_api_key)
    set_router(router)
    print(
        f"[SpriteFlow] Seedream 初始化: model={settings.seedream_model}, "
        f"key_set={'yes' if settings.ark_api_key else 'NO'}"
    )
    print(
        f"[SpriteFlow] Seedance 初始化: model={settings.seedance_model}, "
        f"key_set={'yes' if settings.ark_api_key else 'NO'}"
    )
    print(
        f"[SpriteFlow] OpenRouter 初始化: model={settings.openrouter_default_model}, "
        f"key_set={'yes' if settings.openrouter_api_key else 'NO'}"
    )

    # 初始化执行器
    executor = Executor(
        cache=CacheManager(),
        router=router,
        storage=storage,
        db=db,
    )
    set_executor(executor)

    # 初始化模板数据库
    template_db = TemplateDB()
    await template_db.connect()
    await template_db.init_tables()
    set_template_db(template_db)
    print("[SpriteFlow] 模板数据库初始化成功")

    # 注入预置模板数据（仅首次）
    existing = await template_db.list_specs()
    if not existing:
        spec = PromptBuilder.build_default_spec()
        for layer in spec.layers:
            await template_db.create_layer(layer)
            for block in layer.blocks:
                await template_db.create_block(block, layer.id)
        await template_db.create_spec(spec)

        for c in PromptBuilder.build_default_characters():
            await template_db.create_character(c)
        for a in PromptBuilder.build_default_actions():
            await template_db.create_action(a)
        for v in PromptBuilder.build_default_vfx():
            await template_db.create_vfx(v)

        print("[SpriteFlow] 预置模板数据注入完成: 1 Spec + 6 角色 + 7 动作 + 4 VFX")

    # 启动视频任务后台 worker（独立 asyncio 任务）
    ingest = IngestPipeline(storage=storage, db=db)
    video_worker = VideoWorker(
        db=db,
        ingest=ingest,
        seedance=seedance,
        api_key=settings.ark_api_key,
    )
    video_worker.start()

    yield

    # 清理
    await video_worker.stop()
    await db.close()
    await template_db.close()


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="SpriteFlow",
        description="面向 2D 游戏素材生产的节点化工作流平台",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS：dev 模式前端 :5173 跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(workflows_router, prefix="/api", tags=["workflows"])
    app.include_router(assets_router, prefix="/api", tags=["assets"])
    app.include_router(nodes_router, prefix="/api", tags=["nodes"])
    app.include_router(routing_router, prefix="/api", tags=["routing"])
    app.include_router(generate_router, prefix="/api", tags=["generate"])
    app.include_router(jobs_router, prefix="/api", tags=["jobs"])
    app.include_router(videos_router, prefix="/api", tags=["videos"])
    app.include_router(templates_router, prefix="/api", tags=["templates"])

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": "0.1.0",
            "model": settings.seedream_model,
            "ark_configured": bool(settings.ark_api_key),
        }

    # 兼容旧路径
    @app.get("/health")
    async def health_legacy():
        return await health()

    # 挂载前端静态产物（生产模式）：web/dist
    web_dist = settings.project_root / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")

    return app


app = create_app()
