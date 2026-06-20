"""FastAPI 应用工厂"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
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
from ..templates.seed import PRESET_TEMPLATES
from .deps import set_db, set_storage, set_router, set_executor, set_template_db

# 导入节点以触发注册
from ..nodes import *  # noqa: F401, F403

from .assets import router as assets_router
from .nodes import router as nodes_router
from .routing import router as routing_router
from .generate import router as generate_router
from .jobs import router as jobs_router
from .videos import router as videos_router
from ..templates.api import router as templates_router
from .graphs import router as graphs_router
from .config import router as config_router
from .menu import router as menu_router
from .video_frames import router as video_frames_router
from .image_editor import router as image_editor_router
from .magic import router as magic_router
from ..model_manager.routers.channel_router import router as mm_channel_router
from ..model_manager.routers.route_router import router as mm_route_router
from ..model_manager.database import init_db as init_mm_db
from ..workflow.routers.workflow_router import router as wf_router
from ..workflow.routers.model_router import router as wf_model_router
from ..workflow.routers.app_router import router as wf_app_router
from ..workflow.routers.cost_router import router as cost_router
from ..workflow.database import init_db as init_wf_db
from ..workflow.services.model_settings_service import init_default_settings
from ..workflow.services.model_registry import sync_custom_nodes_to_registry
from ..components.router import router as component_router
from ..components.registry import ComponentRegistry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理"""
    settings.ensure_dirs()

    # ---- API Key 可用性报告 ----
    _print_key_status()

    # 初始化模型管理数据库
    await init_mm_db()

    # 初始化工作流数据库
    await init_wf_db()
    from ..workflow.database import async_session as wf_session
    from ..workflow.services.model_registry import seed_builtin_models_to_db
    async with wf_session() as wf_db:
        await init_default_settings(wf_db)
        await seed_builtin_models_to_db(wf_db)
        await sync_custom_nodes_to_registry(wf_db)
        from ..workflow.workflow_helper import seed_workflow_presets
        await seed_workflow_presets(wf_db)
        await wf_db.commit()

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

    # ----- 从数据库恢复运行时配置（覆盖 routing.yaml 默认值） -----
    await _restore_config_from_db(db, router)
    # ---------------------------------------------------------------

    # ----- 从数据库恢复组件凭据 -----
    await _restore_component_credentials_from_db(db)
    # -------------------------------

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
        f"key_set={'yes' if bool(settings.openrouter_api_key or router._credentials.get('openrouter')) else 'NO'}"
    )

    # 初始化模板数据库（需在 Executor 之前，Executor 依赖 template_db）
    template_db = TemplateDB()
    await template_db.connect()
    await template_db.init_tables()
    set_template_db(template_db)
    print("[SpriteFlow] 模板数据库初始化成功")

    # 初始化执行器
    executor = Executor(
        cache=CacheManager(),
        router=router,
        storage=storage,
        db=db,
        template_db=template_db,
    )
    set_executor(executor)

    # 注入预置模板数据（仅首次）
    count = await template_db.count()
    if not count:
        for t in PRESET_TEMPLATES:
            await template_db.create(t)
        preset_count = len(PRESET_TEMPLATES)
        print(f"[SpriteFlow] 预置模板数据注入完成: {preset_count} 个模板")

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


async def _restore_config_from_db(db, router) -> None:
    """从数据库恢复运行时配置（路由、凭证、Provider 参数）"""
    import json as _json

    # 恢复路由映射
    routes = await db.get_configs_by_prefix("route:")
    for cap, prov in routes.items():
        router.update_route(cap, prov)

    # 恢复回退链
    fallbacks = await db.get_configs_by_prefix("fallback:")
    for cap, raw in fallbacks.items():
        try:
            chain = _json.loads(raw)
            if isinstance(chain, list):
                router.update_fallback(cap, [str(x) for x in chain])
        except _json.JSONDecodeError:
            pass

    # 恢复凭证
    credentials = await db.get_configs_by_prefix("credential:")
    for name, api_key in credentials.items():
        router.update_credential(name, api_key)

    # 恢复 Provider 模型/端点
    for key, value in (await db.get_configs_by_prefix("provider:")).items():
        parts = key.split(":", 1)  # e.g. "openrouter:model" → ["openrouter", "model"]
        if len(parts) == 2:
            name, field = parts
            if field == "model":
                router.update_provider_model(name, value)
            elif field == "base_url":
                router.update_provider_base_url(name, value)

    db_routes = len(routes)
    db_creds = len(credentials)
    if db_routes or db_creds:
        print(f"[SpriteFlow] 从数据库恢复配置: {db_routes} 路由 + {db_creds} 凭证")


async def _restore_component_credentials_from_db(db) -> None:
    """从 config DB 恢复所有组件的凭据到 ComponentRegistry 内存"""
    import json as _json

    try:
        raw = await db.get_configs_by_prefix("component_credential:")
        count = 0
        for cid, json_str in raw.items():
            try:
                creds = _json.loads(json_str) if isinstance(json_str, str) else json_str
                if isinstance(creds, dict):
                    ComponentRegistry.set_credentials(cid, creds)
                    count += 1
            except _json.JSONDecodeError:
                pass
        if count:
            print(f"[SpriteFlow] 从数据库恢复 {count} 个组件凭据")
    except Exception as e:
        print(f"[SpriteFlow] 加载组件凭据失败: {e}")


def _print_key_status() -> None:
    """启动时打印 API Key 配置状态，给出友好提示"""
    missing: list[str] = []
    configured: list[str] = []

    if settings.ark_api_key:
        configured.append("ARK_API_KEY（Seedream + Seedance）")
    else:
        missing.append("ARK_API_KEY — 文生图/图生图/视频生成不可用，请设置环境变量")

    if settings.openrouter_api_key:
        configured.append("OPENROUTER_API_KEY（OpenRouter）")
    else:
        missing.append("OPENROUTER_API_KEY — OpenRouter 多模型路由不可用，请设置环境变量")

    if settings.cos.secret_id and settings.cos.secret_key:
        configured.append("COS 对象存储")
    else:
        missing.append("COS_SECRET_ID / COS_SECRET_KEY — 云存储不可用，将使用本地存储")

    if settings.volc_access_key_id:
        configured.append("火山引擎 AI 图像处理")
    else:
        missing.append("VOLC_ACCESS_KEY_ID — AI 图像增强/修复等功能不可用")

    print("[SpriteFlow] ========== 服务配置状态 ==========")
    for c in configured:
        print(f"  ✅ {c}")
    for m in missing:
        print(f"  ⚠️  {m}")
    print("[SpriteFlow] ====================================")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="SpriteFlow",
        description="面向 2D 游戏素材生产的节点化管线平台",
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

    app.include_router(assets_router, prefix="/api", tags=["assets"])
    app.include_router(nodes_router, prefix="/api", tags=["nodes"])
    app.include_router(routing_router, prefix="/api", tags=["routing"])
    app.include_router(generate_router, prefix="/api", tags=["generate"])
    app.include_router(jobs_router, prefix="/api", tags=["jobs"])
    app.include_router(videos_router, prefix="/api", tags=["videos"])
    app.include_router(templates_router, prefix="/api", tags=["templates"])
    app.include_router(graphs_router, prefix="/api", tags=["graphs"])
    app.include_router(config_router, prefix="/api", tags=["config"])
    app.include_router(menu_router, prefix="/api", tags=["menu"])
    app.include_router(video_frames_router, prefix="/api", tags=["video-frames"])
    app.include_router(image_editor_router, prefix="/api", tags=["image-editor"])
    app.include_router(magic_router, prefix="/api/magic", tags=["magic"])
    app.include_router(mm_channel_router, prefix="/api/model-manager", tags=["model-manager"])
    app.include_router(mm_route_router, prefix="/api/model-manager", tags=["model-manager"])
    app.include_router(wf_router, prefix="/api/workflow", tags=["workflow"])
    app.include_router(wf_model_router, prefix="/api/workflow/models", tags=["workflow-models"])
    app.include_router(wf_app_router, prefix="/api/workflow/app", tags=["workflow-app"])
    app.include_router(cost_router, tags=["cost"])
    app.include_router(component_router)

    @app.api_route("/api/proxy/cos/{path:path}", methods=["GET", "HEAD"])
    async def proxy_cos_resource(path: str, request: Request):
        """代理 COS 资源，解决 CORS 问题"""
        from urllib.parse import unquote
        
        # 解码路径
        decoded_path = unquote(path)
        
        try:
            # 使用 COS SDK 获取文件
            cos_storage = COSStorage()
            content = await cos_storage.download(f"cos://{settings.cos.bucket}/{decoded_path}")
            
            # 根据文件扩展名确定 Content-Type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(decoded_path)
            content_type = mime_type or "application/octet-stream"
            
            # 返回 COS 资源
            return Response(
                content=content,
                status_code=200,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(content)),
                    "Cache-Control": "public, max-age=3600",
                }
            )
        except Exception as e:
            return JSONResponse(
                status_code=404,
                content={"error": f"Failed to fetch COS resource: {str(e)}"}
            )

    @app.api_route("/api/proxy/local/{path:path}", methods=["GET", "HEAD"])
    async def proxy_local_resource(path: str, request: Request):
        """代理本地存储资源，解决 CORS 问题"""
        from urllib.parse import unquote
        
        # 解码路径
        decoded_path = unquote(path)
        
        try:
            # 使用本地存储获取文件
            local_storage = LocalStorage()
            content = await local_storage.download(f"local://{decoded_path}")
            
            # 根据文件扩展名确定 Content-Type
            import mimetypes
            mime_type, _ = mimetypes.guess_type(decoded_path)
            content_type = mime_type or "application/octet-stream"
            
            # 返回本地资源
            return Response(
                content=content,
                status_code=200,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(len(content)),
                    "Cache-Control": "public, max-age=3600",
                }
            )
        except Exception as e:
            return JSONResponse(
                status_code=404,
                content={"error": f"Failed to fetch local resource: {str(e)}"}
            )

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
