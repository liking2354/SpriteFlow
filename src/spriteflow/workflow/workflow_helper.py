"""
Workflow 核心业务层 — 全本地实现

原版所有函数均为透明代理到 api.muapi.ai。
现在所有 23 个函数改为本地数据库 CRUD + AI 服务调用。

所有函数签名新增 db 参数（AsyncSession），从 FastAPI 依赖注入传入。
响应格式完全兼容前端接口契约。
"""
import os
import re
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from sqlalchemy import select as sa_select
from .models import Workflow, RunHistory, ModelConfig, WorkflowPreset, gen_uuid
from .services.model_registry import get_service, get_node_schemas as local_node_schemas
from .services.model_registry import get_api_node_schemas as local_api_schemas
from ..components.registry import ComponentRegistry
from ..config import settings

logger = logging.getLogger(__name__)

# 模板引用正则：匹配 {{ nodeId.outputs[0].value }} 或 {{ nodeId.outputs[0].value  }}
_TEMPLATE_REF_RE = re.compile(
    r"^\{\{\s*(\w+)\.outputs\[(\d+)\]\.value\s*\}\}$"
)

# COS 图片 URL：桶配置为公有读后，去掉预签名查询参数即可直接访问
_COS_BASE_URL = "https://spriteflow-1258748206.cos.ap-guangzhou.myqcloud.com"


def _resolve_template_ref(
    template: str, node_outputs: dict[str, list[dict[str, Any]]]
) -> Any | None:
    """解析模板引用 {{ nodeId.outputs[0].value }}，返回对应节点的输出值。

    例如 {{ image1.outputs[0].value }} 从 image1 节点的 outputs[0].value 取值。
    """
    m = _TEMPLATE_REF_RE.match(template)
    if not m:
        return None
    source_node_id = m.group(1)
    index = int(m.group(2))
    outputs = node_outputs.get(source_node_id, [])
    if index < len(outputs):
        return outputs[index].get("value")
    logger.warning(
        "[workflow] template ref %s resolved but index %d >= len(outputs)=%d",
        template, index, len(outputs),
    )
    return None


def _resolve_edge_params(
    node: dict[str, Any],
    node_outputs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """解析节点的 params 中的模板引用，将上游节点的输出合并到 input_params。

    规则：
    - 遍历 node.params，解析 {{ nodeId.outputs[N].value }} 模板引用
    - 如果对应 key 在 input_params 中不存在或为空，则用解析值填充
    - 保留 input_params 中已有的值（用户手动填写优先于边缘连接）
    """
    input_params = dict(node.get("input_params", {}) or {})
    params_field = node.get("params", {})
    if not params_field:
        return input_params

    injected: dict[str, str] = {}
    for key, value in params_field.items():
        if not isinstance(value, str):
            continue
        resolved = _resolve_template_ref(value, node_outputs)
        if resolved is not None and isinstance(resolved, str) and resolved.strip():
            injected[key] = resolved

    if not injected:
        return input_params

    # 合并：input_params 已有值优先，只有缺失的才用边缘注入
    merged = dict(input_params)
    merge_count = 0
    for key, val in injected.items():
        if key not in merged or not merged[key]:
            merged[key] = val
            merge_count += 1

    if merge_count:
        logger.info(
            "[workflow] edge resolution: node=%s injected=%d keys=%s",
            node.get("id", "?"),
            merge_count,
            list(injected.keys()),
        )
    return merged


def _refresh_cos_urls(params: dict[str, Any]) -> dict[str, Any]:
    """清理 input_params 中 COS URL 的过期签名查询参数。

    桶配置为公有读后，去掉 ?q-sign-* 参数即可直接访问，
    不再需要预签名 URL，也不暴露 SecretId。
    """
    from urllib.parse import urlparse, urlunparse

    url_keys = ["image_url", "image", "video_url", "audio_url", "last_image"]
    refreshed = dict(params)

    for key in url_keys:
        url = refreshed.get(key)
        if isinstance(url, str) and url.startswith(_COS_BASE_URL):
            parsed = urlparse(url)
            if parsed.query:
                clean_url = urlunparse(parsed._replace(query=""))
                refreshed[key] = clean_url
                logger.info(
                    "[workflow] stripped COS signature for key=%s → %s",
                    key, clean_url[:120],
                )

    return refreshed

# 内存缓存：architect 结果（供轮询端点读取）
# key = request_id, value = {nodes, edges, message, suggestions}
_architect_cache: dict = {}


def _store_architect_result(request_id: str, result: dict) -> None:
    """缓存 architect 结果，供 poll 端点读取。最多保留 100 条。"""
    _architect_cache[request_id] = result
    # 清理旧记录：保留最近 100 条
    if len(_architect_cache) > 100:
        oldest = next(iter(_architect_cache))
        del _architect_cache[oldest]


def _pop_architect_result(request_id: str) -> dict | None:
    """获取并清除 architect 缓存结果"""
    return _architect_cache.pop(request_id, None)


# ===========================================================================
# 辅助函数
# ===========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_workflow(db: AsyncSession, workflow_id: str) -> Workflow:
    """获取工作流，不存在则抛 404"""
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id)
    )
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return wf


# ===========================================================================
# 1-7: 工作流 CRUD
# ===========================================================================

async def create_or_update_workflow(db: AsyncSession, payload: dict) -> dict:
    """
    POST /api/workflow/create
    创建或更新工作流
    """
    workflow_id = payload.get("workflow_id") or payload.get("source_workflow_id")

    if workflow_id:
        # 更新已有工作流
        wf = await db.get(Workflow, workflow_id)
    else:
        workflow_id = gen_uuid()
        wf = None

    data = payload.get("data", {})
    edges = payload.get("edges", [])

    if wf:
        # 更新
        wf.name = payload.get("name", wf.name)
        wf.data = data
        wf.edges = edges
        wf.category = payload.get("category", wf.category)
        wf.updated_at = datetime.now(timezone.utc)
    else:
        # 创建
        wf = Workflow(
            id=workflow_id,
            name=payload.get("name", "Untitled"),
            data=data,
            edges=edges,
            category=payload.get("category", "General"),
            is_vadoo=str(payload.get("is_vadoo", "false")).lower(),
        )
        db.add(wf)

    await db.flush()
    return {"workflow_id": workflow_id}


async def get_workflow_defs_helper(db: AsyncSession, limit: int = 20, offset: int = 0) -> dict:
    """
    GET /api/workflow/get-workflow-defs
    返回工作流列表（分页）
    """
    from sqlalchemy import func as sa_func
    
    total_result = await db.execute(select(sa_func.count(Workflow.id)))
    total = total_result.scalar() or 0

    result = await db.execute(
        select(Workflow)
        .order_by(Workflow.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    workflows = result.scalars().all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "workflows": [
            {
                "id": wf.id,
                "name": wf.name,
                "data": wf.data,
                "edges": wf.edges,
                "category": wf.category,
                "thumbnail": wf.thumbnail,
                "is_owner": True,
                "is_published": bool(wf.is_published),
                "is_template": str(wf.category or "").startswith("Template/"),
                "show_temp_button": not str(wf.category or "").startswith("Template/"),
                "created_at": wf.created_at.isoformat() if wf.created_at else _now(),
                "updated_at": wf.updated_at.isoformat() if wf.updated_at else _now(),
            }
            for wf in workflows
        ],
    }


async def get_workflow_def_helper(db: AsyncSession, workflow_id: str) -> dict:
    """
    GET /api/workflow/get-workflow-def/{id}
    返回工作流详情（含最近运行 run_id，用于恢复运行态）
    """
    wf = await _get_workflow(db, workflow_id)

    # 查询最近一次运行的 run_id（如果仍有节点在 running，前端需要恢复轮询）
    run_id = None
    result = await db.execute(
        select(RunHistory.run_id)
        .where(RunHistory.workflow_id == workflow_id)
        .order_by(RunHistory.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if row:
        run_id = row[0]

    return {
        "id": wf.id,
        "name": wf.name,
        "data": wf.data,
        "edges": wf.edges,
        "category": wf.category,
        "thumbnail": wf.thumbnail,
        "is_owner": True,
        "is_published": bool(wf.is_published),
        "is_template": str(wf.category or "").startswith("Template/"),
        "show_temp_button": not str(wf.category or "").startswith("Template/"),
        "created_at": wf.created_at.isoformat() if wf.created_at else _now(),
        "updated_at": wf.updated_at.isoformat() if wf.updated_at else _now(),
        "run_id": run_id,
    }


async def delete_workflow_def_by_id(db: AsyncSession, workflow_id: str) -> dict:
    """
    DELETE /api/workflow/delete-workflow-def/{id}
    删除工作流及其运行历史
    """
    wf = await _get_workflow(db, workflow_id)

    # 删除关联的运行历史
    await db.execute(
        delete(RunHistory).where(RunHistory.workflow_id == workflow_id)
    )
    await db.delete(wf)
    await db.flush()
    return {"detail": "Workflow deleted successfully"}


async def update_workflow_name_helper(db: AsyncSession, workflow_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/update-name/{id}
    重命名工作流
    """
    wf = await _get_workflow(db, workflow_id)
    wf.name = payload.get("name", wf.name)
    wf.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"detail": "Name updated"}


async def update_workflow_category_helper(db: AsyncSession, workflow_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/update-category/{id}
    更新分类
    """
    wf = await _get_workflow(db, workflow_id)
    wf.category = payload.get("category", wf.category)
    wf.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"detail": "Category updated"}


# ===========================================================================
# 8-12: AI 执行
# ===========================================================================

async def run_workflow_helper(db: AsyncSession, workflow_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/{id}/run
    准备工作流运行记录并立即返回 run_id，实际执行由 BackgroundTasks 异步完成
    """
    wf = await _get_workflow(db, workflow_id)
    run_id = gen_uuid()

    # 创建工作流运行记录（初始状态 pending）
    nodes_data = wf.data.get("nodes", []) if isinstance(wf.data, dict) else []

    for node in nodes_data:
        node_id = node.get("id", "")
        node_run = RunHistory(
            id=gen_uuid(),
            workflow_id=workflow_id,
            node_id=node_id,
            run_id=run_id,
            node_run_id=gen_uuid(),
            status="running",  # 初始即 running，前端轮询能立即看到运行态
            node_data=node,
        )
        db.add(node_run)

    await db.flush()
    await db.commit()  # 必须提交，否则后台任务会遇到 SQLite 数据库锁
    return {"run_id": run_id, "nodes_data": nodes_data, "workflow_id": workflow_id}


async def execute_workflow_run(
    run_id: str,
    workflow_id: str,
    nodes_data: list[dict[str, Any]],
) -> None:
    """
    后台异步执行工作流所有节点。

    使用独立的数据库会话，逐个执行节点并在每次执行前后更新 RunHistory 状态。
    前端通过 GET /api/workflow/run/{run_id}/status 轮询状态变化。
    """
    from .database import async_session as _async_session

    # 维护已执行节点的输出，用于解析下游节点的边缘引用
    node_outputs: dict[str, list[dict[str, Any]]] = {}

    for node in nodes_data:
        node_id = node.get("id", "")
        result: dict[str, Any] | None = None
        status = "running"

        async with _async_session() as bg_db:
            try:
                model_id = node.get("model", "")
                category = node.get("category", "")
                form_values = node.get("formValues", {})

                # 从 input_params 读取基础参数（表单填写的值）
                input_params_raw = node.get("input_params", {}) or form_values or {}

                # 解析 params 中的模板引用（{{ upstreamNode.outputs[0].value }}），
                # 将上游节点输出注入到 input_params 中缺失的字段
                input_params = _resolve_edge_params(node, node_outputs)

                # input_params 至少要有基础数据
                if not input_params:
                    input_params = dict(input_params_raw)

                logger.info(
                    "[workflow] executing node=%s model=%s input_keys=%s",
                    node_id, model_id, list(input_params.keys()),
                )

                # ---- passthrough 节点 ----
                if model_id.endswith("-passthrough") or model_id in ("text-passthrough", "image-passthrough", "video-passthrough", "audio-passthrough"):
                    field_keys = ["prompt", "image_url", "video_url", "audio_url"]
                    found = False
                    for key in field_keys:
                        if key in input_params and input_params[key]:
                            type_map = {"prompt": "text", "image_url": "image_url", "video_url": "video_url", "audio_url": "audio_url"}
                            output_type = type_map.get(key, "text")
                            result = {"outputs": [{"type": output_type, "value": input_params[key]}]}
                            status = "succeeded"
                            found = True
                            break
                    if not found:
                        result = {"outputs": [{"type": "text", "value": str(input_params)}]}
                        status = "succeeded"

                # ---- utility 节点 ----
                elif category == "utility" or model_id == "prompt-concatenator":
                    prompts = input_params.get("prompts", [])
                    if isinstance(prompts, list):
                        prompt_val = "\n\n".join([str(p.get("value", p)) if isinstance(p, dict) else str(p) for p in prompts])
                    else:
                        prompt_val = input_params.get("prompt", "")
                    result = {"outputs": [{"type": "text", "value": prompt_val}]}
                    status = "succeeded"

                # ---- video-combiner 节点 ----
                elif model_id == "video-combiner":
                    videos = input_params.get("videos_list", [])
                    aspect_ratio = input_params.get("aspect_ratio", "auto")
                    result = {"outputs": [{"type": "text", "value": f"Video Combiner: {len(videos)} clips, aspect_ratio={aspect_ratio}."}]}
                    status = "succeeded"

                # ---- 常规 AI 服务 ----
                else:
                    service = get_service(model_id)
                    if service:
                        result = await service.generate(input_params, model=model_id)
                        status = "succeeded"
                    else:
                        # ComponentRegistry 回退
                        component = ComponentRegistry.get(model_id)
                        if component:
                            try:
                                # 优先使用组件管理页配置的凭据，缺失回退到 .env
                                component_credentials = ComponentRegistry.get_credentials(model_id)
                                # 刷新 COS 预签名 URL（避免下游 API 无法下载参考图）
                                resolved_params = _refresh_cos_urls(input_params)
                                result = await component.execute(inputs=resolved_params, params=resolved_params, credentials=component_credentials)
                                status = "succeeded"
                                logger.info(f"Custom component {model_id} executed in workflow run")
                            except Exception as comp_err:
                                result = {"outputs": [{"type": "text", "value": f"组件执行失败: {str(comp_err)}"}]}
                                status = "failed"
                                logger.error(f"Custom component {model_id} failed: {comp_err}")
                        else:
                            result = {"outputs": [{"type": "text", "value": f"Model '{model_id}' not configured locally. Configure AI provider in .env."}]}
                            status = "failed"

            except Exception as e:
                logger.error(f"Error running node {node_id}: {e}")
                result = {"outputs": [{"type": "text", "value": f"Error: {str(e)}"}]}
                status = "failed"

            # 存储节点输出，供下游节点解析边缘引用
            if result and isinstance(result, dict):
                outputs_list = result.get("outputs", [])
                if outputs_list:
                    node_outputs[node_id] = outputs_list

            # 更新运行记录
            await bg_db.execute(
                update(RunHistory)
                .where(RunHistory.run_id == run_id, RunHistory.node_id == node_id)
                .values(status=status, result=result, updated_at=datetime.now(timezone.utc))
            )
            await bg_db.commit()

    logger.info("[workflow] run_id=%s all nodes executed", run_id)


async def run_node_helper(db: AsyncSession, workflow_id: str, node_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/{id}/node/{nid}/run
    运行单个节点
    """
    _ = await _get_workflow(db, workflow_id)
    node_run_id = gen_uuid()
    run_id = gen_uuid()

    model_id = payload.get("model", "")
    input_params = payload.get("input_params", payload.get("params", {}))
    category = payload.get("category", "")

    # 创建运行记录
    node_run = RunHistory(
        id=gen_uuid(),
        workflow_id=workflow_id,
        node_id=node_id,
        run_id=run_id,
        node_run_id=node_run_id,
        status="running",
        node_data=payload,
    )
    db.add(node_run)
    await db.flush()

    # 处理 passthrough 节点（直接透传输入）
    if model_id.endswith("-passthrough") or model_id in ("text-passthrough", "image-passthrough", "video-passthrough", "audio-passthrough"):
        # 透传：直接返回输入值
        field_keys = ["prompt", "image_url", "video_url", "audio_url"]
        for key in field_keys:
            if key in input_params:
                type_map = {"prompt": "text", "image_url": "image_url", "video_url": "video_url", "audio_url": "audio_url"}
                output_type = type_map.get(key, "text")
                result = {"outputs": [{"type": output_type, "value": input_params[key]}]}
                node_run.status = "succeeded"
                node_run.result = result
                node_run.updated_at = datetime.now(timezone.utc)
                await db.flush()
                return {"run_id": run_id, "node_run_id": node_run_id}

        # 默认返回第一个有值的字段
        output_val = input_params.get("prompt", str(input_params))
        result = {"outputs": [{"type": "text", "value": output_val}]}
        node_run.status = "succeeded"
        node_run.result = result
        node_run.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return {"run_id": run_id, "node_run_id": node_run_id}

    # 处理 utility 节点（纯本地逻辑）
    if category == "utility" or model_id == "prompt-concatenator":
        # 文本拼接节点
        prompts = input_params.get("prompts", [])
        if isinstance(prompts, list):
            prompt_val = "\n\n".join([str(p.get("value", p)) if isinstance(p, dict) else str(p) for p in prompts])
        else:
            prompt_val = input_params.get("prompt", "")
        result = {"outputs": [{"type": "text", "value": prompt_val}]}
        node_run.status = "succeeded"
        node_run.result = result
        node_run.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return {"run_id": run_id, "node_run_id": node_run_id}

    # 处理 video-combiner 节点
    if model_id == "video-combiner":
        videos = input_params.get("videos_list", [])
        aspect_ratio = input_params.get("aspect_ratio", "auto")
        result = {
            "outputs": [
                {
                    "type": "text",
                    "value": f"Video Combiner: {len(videos)} clips, aspect_ratio={aspect_ratio}. " +
                             "Video combining is processed locally. Configure an external combiner service in production."
                }
            ]
        }
        node_run.status = "succeeded"
        node_run.result = result
        node_run.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return {"run_id": run_id, "node_run_id": node_run_id}

    try:
        service = get_service(model_id)
        if service:
            result = await service.generate(input_params, model=model_id)
            node_run.status = "succeeded"
            node_run.result = result
        else:
            # 尝试从 ComponentRegistry 查找自定义组件
            component = ComponentRegistry.get(model_id)
            if component:
                try:
                    # 优先使用组件管理页配置的凭据，缺失回退到 .env
                    component_credentials = ComponentRegistry.get_credentials(model_id)
                    # 刷新 COS 预签名 URL（避免下游 API 无法下载参考图）
                    resolved_params = _refresh_cos_urls(input_params)
                    # 自定义组件的 execute(inputs, params, credentials)
                    # input_params 包含所有参数，组件自己区分 inputs/params
                    result = await component.execute(
                        inputs=resolved_params,
                        params=resolved_params,
                        credentials=component_credentials,
                    )
                    node_run.status = "succeeded"
                    node_run.result = result
                    logger.info(f"Custom component {model_id} executed successfully")
                except Exception as comp_err:
                    node_run.status = "failed"
                    node_run.result = {
                        "outputs": [
                            {"type": "text", "value": f"组件执行失败: {str(comp_err)}"}
                        ]
                    }
                    logger.error(f"Custom component {model_id} failed: {comp_err}")
            else:
                # 未配置的服务 → 返回友好提示
                node_run.status = "failed"
                node_run.result = {
                    "outputs": [
                        {
                            "type": "text",
                            "value": f"模型 '{model_id}' 未在本地配置。请在 .env 中配置对应的 AI 提供商 (OPENAI_API_KEY / REPLICATE_API_TOKEN / OLLAMA_HOST)。"
                        }
                    ]
                }
                logger.warning(f"No local service configured for model: {model_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Node run error for {model_id}: {e}")
        node_run.status = "failed"
        node_run.result = {
            "outputs": [{"type": "text", "value": f"运行失败: {str(e)}"}]
        }

    node_run.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"run_id": run_id, "node_run_id": node_run_id}


async def get_run_status_helper(db: AsyncSession, run_id: str) -> dict:
    """
    GET /api/workflow/run/{run_id}/status
    轮询运行状态
    """
    result = await db.execute(
        select(RunHistory).where(RunHistory.run_id == run_id)
    )
    runs = result.scalars().all()

    # 按节点分组
    nodes_status: dict[str, list] = {}
    for r in runs:
        node_id = r.node_id or "unknown"
        entry = {
            "status": r.status or "pending",
            "result": r.result or {"id": gen_uuid(), "outputs": []},
            "node_run_id": r.node_run_id or gen_uuid(),
        }
        if node_id not in nodes_status:
            nodes_status[node_id] = []
        nodes_status[node_id].append(entry)

    return {"nodes": nodes_status}


async def delete_node_run_by_id_helper(db: AsyncSession, node_run_id: str) -> dict:
    """
    DELETE /api/workflow/node-run/{node_run_id}
    删除节点运行历史
    """
    await db.execute(
        delete(RunHistory).where(RunHistory.node_run_id == node_run_id)
    )
    await db.flush()
    return {"detail": "Node run deleted"}


async def get_workflow_last_run(db: AsyncSession, workflow_id: str) -> dict:
    """
    GET /api/workflow/get-workflow-last-run/{id}
    获取工作流最后运行记录
    """
    result = await db.execute(
        select(RunHistory)
        .where(RunHistory.workflow_id == workflow_id)
        .order_by(RunHistory.created_at.desc())
        .limit(50)
    )
    runs = result.scalars().all()

    if not runs:
        return {}

    latest_run_id = runs[0].run_id

    nodes_status: dict[str, list] = {}
    for r in runs:
        if r.run_id != latest_run_id:
            continue
        node_id = r.node_id or "unknown"
        entry = {
            "status": r.status,
            "result": r.result,
            "node_run_id": r.node_run_id,
        }
        if node_id not in nodes_status:
            nodes_status[node_id] = []
        nodes_status[node_id].append(entry)

    return {"run_id": latest_run_id, "nodes": nodes_status}


# ===========================================================================
# 13-14: 模型 Schema
# ===========================================================================

async def get_node_schemas_helper(workflow_id: str, db: AsyncSession = None) -> dict:
    """
    GET /api/workflow/{id}/node-schemas
    返回本地模型 Schema，可选按 DB 可见性配置过滤
    """
    # 查询哪些模型被标记为不可见
    hidden_models = set()
    if db is not None:
        result = await db.execute(
            sa_select(ModelConfig.model_id).where(ModelConfig.is_visible == "false")
        )
        hidden_models = set(row[0] for row in result.fetchall())

    if hidden_models:
        all_schema = local_node_schemas(workflow_id)
        for cat_key in list(all_schema["categories"].keys()):
            models = all_schema["categories"][cat_key]["models"]
            filtered = {k: v for k, v in models.items() if k not in hidden_models}
            all_schema["categories"][cat_key]["models"] = filtered
        return all_schema

    return local_node_schemas(workflow_id)


async def get_api_node_schemas_helper(_workflow_id: str) -> dict:
    """
    GET /api/workflow/{id}/api-node-schemas
    返回 API 连接器 Schema
    """
    return local_api_schemas(_workflow_id)


# ===========================================================================
# 15-16: AI 对话助手
# ===========================================================================

async def architect_workflow_helper(payload: dict) -> dict:
    """
    POST /api/workflow/architect
    AI 构建工作流 — 支持用户指定模型，优先模型管理器配置，回退到环境变量

    1. 如果 payload 包含 model_id，从模型管理器查找该模型的通道配置
    2. 否则查找 text 类型默认模型的通道配置
    3. 如果未配置，回退到 settings.openai_api_key
    """
    prompt = payload.get("prompt", "")
    workflow_id = payload.get("workflow_id", "")
    user_model_id = payload.get("model_id", "")  # 用户选择的模型

    # ── 尝试从模型管理器获取通道配置 ──
    api_key = settings.openai_api_key
    base_url = settings.openai_base_url
    model_name = "gpt-4o-mini"
    channel_info = None

    try:
        from ..model_manager.database import async_session as mm_session
        from ..model_manager.services.route_service import get_default_text_model_config, get_model_channel_config
        async with mm_session() as mm_db:
            if user_model_id:
                channel_info = await get_model_channel_config(mm_db, user_model_id)
            if not channel_info:
                channel_info = await get_default_text_model_config(mm_db)
    except Exception:
        pass  # 模型管理器不可用时静默回退

    if channel_info and channel_info.get("api_key"):
        api_key = channel_info["api_key"]
        base_url = channel_info["base_url"]
        model_name = channel_info["model"]
        logger.info(f"Architect using model: {model_name} (model_id={channel_info.get('model_id')}, channel={channel_info.get('channel_name')})")
    elif not api_key:
        request_id = gen_uuid()
        _store_architect_result(request_id, {
            "message": "AI 工作流构建需要配置 API Key。请在「模型管理」中为 text 类型设置默认模型的通道，或在 .env 中设置 OPENAI_API_KEY。",
            "workflow": {"nodes": [], "edges": []},
            "suggestions": [],
        })
        return {
            "request_id": request_id,
            "status": "completed",
            "result": {
                "nodes": [],
                "edges": [],
                "message": "AI 工作流构建需要配置 API Key。请在「模型管理」中为 text 类型设置默认模型的通道，或在 .env 中设置 OPENAI_API_KEY。"
            }
        }

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        # ── 动态获取注册表中实际的模型列表 ──
        schemas = local_node_schemas("")
        categories = schemas.get("categories", {})

        model_lines = []
        for cat_key in ["text", "image", "video", "audio", "utility"]:
            cat_data = categories.get(cat_key, {})
            models = cat_data.get("models", {})
            # 过滤掉 passthrough 节点，只列出生成型模型
            model_ids = [mid for mid in models if "passthrough" not in mid]
            if model_ids:
                model_lines.append(f"- {cat_key}: {', '.join(model_ids)}")
        model_list = "\n".join(model_lines)

        system_prompt = f"""You are a workflow builder for a 2D game asset production platform. Given a natural language description, output a JSON workflow with nodes and edges.

Available node categories and their models (use EXACT model IDs as listed):
{model_list}

Handles (input/output port names):
- textNode: textOutput
- imageNode: imageOutput
- videoNode: videoOutput
- audioNode: audioOutput
- concatNode: concatOutput
- Text input: textInput
- Image input: imageInput
- Video input: videoInput
- Audio input: audioInput2
- Concat input: concatInput

Output format (only valid JSON, no markdown):
{{
  "nodes": [
    {{"id": "node_1", "category": "text|image|video|audio|utility", 
     "model": "use EXACT model ID from the list above", 
     "position": {{"x": 0, "y": 0}}, 
     "formValues": {{"prompt": "the actual prompt content"}}}}
  ],
  "edges": [
    {{"id": "edge_1", "source": "node_1", "target": "node_2", 
     "sourceHandle": "textOutput", "targetHandle": "imageInput"}}
  ]
}}

Rules:
1. Always output real, useful workflow nodes — never echo the user's question as a prompt.
2. If the user asks a question (e.g. "who are you", "what model are you"), respond with a message field explaining your capability and suggest a demo workflow.
3. Use {{"message": "..."}} at top level for conversational responses (no nodes needed).
4. Position nodes with reasonable x,y spacing (e.g., x: 0, 350, 700 for sequential flows).
5. Default to text->image->video pipeline when the user is vague.
6. CRITICAL: Use EXACT model IDs from the list above. Do NOT invent or guess model names."""

        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Build a workflow for: {prompt}"}
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        import json
        result = json.loads(response.choices[0].message.content)

        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        ai_message = result.get("message", "")

        # Generate a meaningful message if AI didn't provide one but returned nodes
        if not ai_message and nodes:
            ai_message = f"已为你创建了包含 {len(nodes)} 个节点的工作流。你可以在画布上查看和编辑。"

        request_id = gen_uuid()
        _store_architect_result(request_id, {
            "message": ai_message,
            "workflow": {
                "nodes": nodes,
                "edges": edges,
            },
            "suggestions": result.get("suggestions", []),
        })

        return {
            "request_id": request_id,
            "status": "completed",
            "result": result
        }

    except Exception as e:
        logger.error(f"Architect error: {e}")
        request_id = gen_uuid()
        _store_architect_result(request_id, {
            "message": f"AI 构建失败: {str(e)}",
            "workflow": {"nodes": [], "edges": []},
            "suggestions": [],
        })
        return {
            "request_id": request_id,
            "status": "completed",
            "result": {
                "nodes": [],
                "edges": [],
                "message": f"AI 构建失败: {str(e)}"
            }
        }


async def poll_architect_result_helper(id: str) -> dict:
    """
    GET /api/workflow/poll-architect/{id}/result
    轮询 AI 构建结果 — 从内存缓存读取 architect 返回的数据
    """
    cached = _pop_architect_result(id)
    if cached:
        return {
            "status": "completed",
            "message": cached.get("message", ""),
            "workflow": cached.get("workflow"),
            "suggestions": cached.get("suggestions", []),
        }
    # 缓存未命中（可能已过期或被清理），返回通用完成状态
    return {
        "status": "completed",
        "message": "",
        "workflow": {"nodes": [], "edges": []},
        "suggestions": [],
    }


# ===========================================================================
# 17-18: 发布与模板
# ===========================================================================

async def publish_workflow_helper(db: AsyncSession, workflow_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/workflow/{id}/publish
    发布工作流为 API — 本地版存储发布元数据
    """
    wf = await _get_workflow(db, workflow_id)
    publish = payload.get("publish", not wf.is_published)
    wf.is_published = publish
    await db.flush()
    return {
        "workflow_id": workflow_id,
        "publish": publish,
        "message": "Workflow published locally. API endpoint available at /api/workflow/{id}/api-execute"
    }


async def template_workflow_helper(db: AsyncSession, workflow_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/workflow/{id}/template
    保存为模板 — 本地版标记工作流为模板
    """
    wf = await _get_workflow(db, workflow_id)
    # 简单标记：将 category 设为 "Template/<原分类>"
    template_name = payload.get("name", wf.name)
    wf.category = f"Template/{wf.category}"
    wf.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "workflow_id": workflow_id,
        "template_name": template_name,
        "message": "Template saved locally"
    }


# ===========================================================================
# 19-21: 文件与媒体
# ===========================================================================

async def cloudfront_signed_url_helper(payload: dict) -> dict:
    """
    POST /api/workflow/cloudfront-signed-url
    获取签名 URL — 本地版直接返回原始 URL（无 CDN）
    """
    file_url = payload.get("url", "")
    # 本地模式下直接返回原 URL，无需签名
    signed_url = file_url

    # 如果是本地文件路径，转为静态文件 URL
    upload_dir = settings.upload_dir
    if file_url.startswith(upload_dir) or file_url.startswith("./uploads"):
        filename = os.path.basename(file_url)
        signed_url = f"{settings.static_url_prefix}/{filename}"

    return {"signed_url": signed_url or file_url}


async def generate_thumbnail_helper(db: AsyncSession, workflow_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/{id}/thumbnail
    设置封面图
    """
    wf = await _get_workflow(db, workflow_id)
    thumbnail_url = payload.get("thumbnail", "") or payload.get("url", "")
    wf.thumbnail = thumbnail_url
    wf.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"thumbnail": thumbnail_url, "detail": "Thumbnail updated"}


async def get_file_upload_url_helper(params: dict) -> dict:
    """
    GET /api/app/get_file_upload_url
    获取文件上传 URL — 本地版返回本地存储路径
    """
    filename = params.get("filename", f"upload_{gen_uuid()[:8]}")
    content_type = params.get("content_type", "application/octet-stream")

    # 确保上传目录存在
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)

    upload_path = os.path.join(upload_dir, filename)
    upload_url = f"/api/app/upload/{filename}"

    return {
        "upload_url": upload_url,
        "file_path": upload_path,
        "filename": filename,
        "content_type": content_type,
    }


# ===========================================================================
# 22-23: API 端点
# ===========================================================================

async def get_workflow_api_inputs_helper(db: AsyncSession, workflow_id: str) -> dict:
    """
    GET /api/workflow/{id}/api-inputs
    获取工作流 API 入参定义
    """
    wf = await _get_workflow(db, workflow_id)
    nodes = wf.data.get("nodes", []) if isinstance(wf.data, dict) else []

    inputs = {}
    for node in nodes:
        node_id = node.get("id", "")
        input_params = node.get("input_params", {})
        if input_params:
            inputs[node_id] = input_params

    return {"workflow_id": workflow_id, "inputs": inputs}


async def execute_workflow_via_api_helper(db: AsyncSession, workflow_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/{id}/api-execute
    通过 API 方式执行工作流
    """
    # 委托给 run_workflow_helper
    return await run_workflow_helper(db, workflow_id, payload)


async def get_workflow_api_outputs_helper(db: AsyncSession, run_id: str) -> dict:
    """
    GET /api/workflow/run/{run_id}/api-outputs
    获取 API 执行输出
    """
    status = await get_run_status_helper(db, run_id)
    return status


# ===========================================================================
# 工作流预设模板 CRUD
# ===========================================================================

PRESET_SEED_DATA = [
    {
        "preset_id": "empty-workflow",
        "title": "Empty Workflow",
        "description": "",
        "icon": "plus",
        "image": "",
        "category": "General",
        "nodes": [],
        "edges": [],
        "sort_order": "0",
    },
    {
        "preset_id": "image-generator",
        "title": "Image Generator & Editor",
        "description": "Simple text to image Generation and Editing with Wan 2.5",
        "icon": "image",
        "image": "https://cdn.muapi.ai/assets/demos/bbb516800e1145f09b9a109d73afbe2c.png",
        "category": "General",
        "sort_order": "1",
        "nodes": [
            {
                "id": "text1",
                "position": {"x": -69, "y": 22},
                "data": {
                    "selectedModel": {"id": "text-passthrough", "name": "Input Text"},
                    "formValues": {
                        "prompt": "Ultra-detailed cinematic portrait of a futuristic AI engineer inside a holographic command center. Floating transparent UI panels, glowing blue and violet data streams, reflective surfaces, soft rim lighting, shallow depth of field, realistic skin texture, high-end sci-fi film aesthetic, 8K resolution, photorealistic, dramatic contrast, clean futuristic design."
                    },
                    "outputs": [{"type": "text", "value": "Ultra-detailed cinematic portrait of a futuristic AI engineer inside a holographic command center. Floating transparent UI panels, glowing blue and violet data streams, reflective surfaces, soft rim lighting, shallow depth of field, realistic skin texture, high-end sci-fi film aesthetic, 8K resolution, photorealistic, dramatic contrast, clean futuristic design."}],
                    "resultUrl": "Ultra-detailed cinematic portrait of a futuristic AI engineer inside a holographic command center. Floating transparent UI panels, glowing blue and violet data streams, reflective surfaces, soft rim lighting, shallow depth of field, realistic skin texture, high-end sci-fi film aesthetic, 8K resolution, photorealistic, dramatic contrast, clean futuristic design."
                },
                "type": "textNode"
            },
            {
                "id": "image1",
                "position": {"x": 370, "y": 250},
                "data": {
                    "selectedModel": {"id": "wan2.5-text-to-image", "name": "Wan 2.5 Text to Image"},
                    "formValues": {"prompt": "Ultra-detailed cinematic portrait of a futuristic AI engineer inside a holographic command center. Floating transparent UI panels, glowing blue and violet data streams, reflective surfaces, soft rim lighting, shallow depth of field, realistic skin texture, high-end sci-fi film aesthetic, 8K resolution, photorealistic, dramatic contrast, clean futuristic design.", "width": 1024, "height": 1024},
                    "outputs": [{"type": "image_url", "value": "https://cdn.muapi.ai/assets/demos/6e3f3a27d9d14d978fb9c22aa2289a7c.png"}],
                    "resultUrl": "https://cdn.muapi.ai/assets/demos/6e3f3a27d9d14d978fb9c22aa2289a7c.png"
                },
                "type": "imageNode"
            },
            {
                "id": "text2",
                "position": {"x": 390, "y": -235},
                "data": {
                    "selectedModel": {"id": "text-passthrough", "name": "Input Text"},
                    "formValues": {"prompt": "Enhance the lighting to be more cinematic with stronger rim light and subtle volumetric fog. Increase contrast and depth, add more glowing holographic elements around the subject, slightly darken the background for focus, improve facial realism and sharpness, maintain photorealistic style and premium sci-fi mood."},
                    "outputs": [{"type": "text", "value": "Enhance the lighting to be more cinematic with stronger rim light and subtle volumetric fog. Increase contrast and depth, add more glowing holographic elements around the subject, slightly darken the background for focus, improve facial realism and sharpness, maintain photorealistic style and premium sci-fi mood."}],
                    "resultUrl": "Enhance the lighting to be more cinematic with stronger rim light and subtle volumetric fog. Increase contrast and depth, add more glowing holographic elements around the subject, slightly darken the background for focus, improve facial realism and sharpness, maintain photorealistic style and premium sci-fi mood."
                },
                "type": "textNode"
            },
            {
                "id": "image2",
                "position": {"x": 835, "y": 25},
                "data": {
                    "selectedModel": {"id": "wan2.5-image-edit", "name": "Wan 2.5 Image Edit"},
                    "formValues": {"prompt": "Enhance the lighting to be more cinematic with stronger rim light and subtle volumetric fog. Increase contrast and depth, add more glowing holographic elements around the subject, slightly darken the background for focus, improve facial realism and sharpness, maintain photorealistic style and premium sci-fi mood.", "images_list": ["https://cdn.muapi.ai/assets/demos/6e3f3a27d9d14d978fb9c22aa2289a7c.png"], "width": 2048, "height": 2048},
                    "outputs": [{"type": "image_url", "value": "https://cdn.muapi.ai/assets/demos/bbb516800e1145f09b9a109d73afbe2c.png"}],
                    "resultUrl": "https://cdn.muapi.ai/assets/demos/bbb516800e1145f09b9a109d73afbe2c.png"
                },
                "type": "imageNode"
            }
        ],
        "edges": [
            {"id": "e1-1", "source": "text1", "target": "image1", "sourceHandle": "textOutput", "targetHandle": "imageInput", "style": {"stroke": "#3b82f6", "strokeWidth": 2}},
            {"id": "e1-2", "source": "image1", "target": "image2", "sourceHandle": "imageOutput", "targetHandle": "imageInput2", "style": {"stroke": "#22c55e", "strokeWidth": 2}},
            {"id": "e1-3", "source": "text2", "target": "image2", "sourceHandle": "textOutput", "targetHandle": "imageInput", "style": {"stroke": "#3b82f6", "strokeWidth": 2}}
        ]
    },
    {
        "preset_id": "video-generator",
        "title": "Video Generator",
        "description": "Simple Video Generation with Seedance Lite",
        "icon": "video",
        "image": "https://cdn.muapi.ai/assets/demos/3283a83b5e374ca781f298b04a9e7640.png",
        "category": "General",
        "sort_order": "2",
        "nodes": [
            {
                "id": "text1",
                "position": {"x": -9, "y": 30},
                "data": {
                    "selectedModel": {"id": "text-passthrough", "name": "Input Text"},
                    "formValues": {"prompt": "Animate the scene with slow cinematic camera movement, subtle parallax, and smooth forward motion. Holographic elements gently pulse and shift, light rays move naturally through fog, floating structures subtly rotate, ultra-smooth transitions, realistic motion blur, film-grade animation, cinematic pacing, premium tech showcase style."},
                    "outputs": [{"type": "text", "value": "Animate the scene with slow cinematic camera movement, subtle parallax, and smooth forward motion. Holographic elements gently pulse and shift, light rays move naturally through fog, floating structures subtly rotate, ultra-smooth transitions, realistic motion blur, film-grade animation, cinematic pacing, premium tech showcase style."}],
                    "resultUrl": "Animate the scene with slow cinematic camera movement, subtle parallax, and smooth forward motion. Holographic elements gently pulse and shift, light rays move naturally through fog, floating structures subtly rotate, ultra-smooth transitions, realistic motion blur, film-grade animation, cinematic pacing, premium tech showcase style."
                },
                "type": "textNode"
            },
            {
                "id": "image1",
                "position": {"x": -14, "y": -426},
                "data": {
                    "selectedModel": {"id": "bytedance-seedream-v4.5", "name": "Seedream v4.5"},
                    "formValues": {"prompt": "Wide cinematic shot of a glowing futuristic city built from floating geometric shapes and holographic panels. Neon blue and purple lights, soft volumetric fog, reflective surfaces, dramatic sky, ultra-realistic lighting, depth of field, 8K detail, sci-fi cinematic style, symmetrical composition.", "aspect_ratio": "1:1", "quality": "high"},
                    "outputs": [{"type": "image_url", "value": "https://cdn.muapi.ai/assets/demos/3283a83b5e374ca781f298b04a9e7640.png"}],
                    "resultUrl": "https://cdn.muapi.ai/assets/demos/3283a83b5e374ca781f298b04a9e7640.png"
                },
                "type": "imageNode"
            },
            {
                "id": "video1",
                "position": {"x": 624, "y": -154},
                "data": {
                    "selectedModel": {"id": "seedance-lite-i2v", "name": "Seedance Lite I2V"},
                    "formValues": {"prompt": "Animate the scene with slow cinematic camera movement, subtle parallax, and smooth forward motion. Holographic elements gently pulse and shift, light rays move naturally through fog, floating structures subtly rotate, ultra-smooth transitions, realistic motion blur, film-grade animation, cinematic pacing, premium tech showcase style.", "image_url": "https://cdn.muapi.ai/assets/demos/3283a83b5e374ca781f298b04a9e7640.png", "resolution": "720p", "duration": 5, "camera_fixed": False},
                    "outputs": [{"type": "video_url", "value": "https://cdn.muapi.ai/assets/demos/91b35ba94f75485c8f196c5a91c14d68.mp4"}],
                    "resultUrl": "https://cdn.muapi.ai/assets/demos/91b35ba94f75485c8f196c5a91c14d68.mp4"
                },
                "type": "videoNode"
            }
        ],
        "edges": [
            {"id": "e1-1", "source": "text1", "target": "video1", "sourceHandle": "textOutput", "targetHandle": "videoInput", "style": {"stroke": "#3b82f6", "strokeWidth": 2}},
            {"id": "e1-2", "source": "image1", "target": "video1", "sourceHandle": "imageOutput", "targetHandle": "videoInput2", "style": {"stroke": "#22c55e", "strokeWidth": 2}}
        ]
    },
    {
        "preset_id": "audio-generator",
        "title": "Audio Generator",
        "description": "Generate audio from text with Suno",
        "icon": "audio",
        "image": "https://images.unsplash.com/photo-1526512340740-9217d0159da9?q=80&w=500&auto=format&fit=crop",
        "category": "General",
        "sort_order": "3",
        "nodes": [
            {
                "id": "text1",
                "position": {"x": -9, "y": 30},
                "data": {
                    "selectedModel": {"id": "text-passthrough", "name": "Input Text"},
                    "formValues": {"prompt": "Generate a cinematic ambient soundscape with deep atmospheric pads, soft evolving synth textures, subtle low-frequency pulses, and gentle high-end shimmer. The mood should feel futuristic, calm, and inspirational, suitable for a high-end AI product or cinematic workflow reveal. Clean mix, professional sound design, smooth transitions, no abrupt sounds."},
                    "outputs": [{"type": "text", "value": "Generate a cinematic ambient soundscape with deep atmospheric pads, soft evolving synth textures, subtle low-frequency pulses, and gentle high-end shimmer. The mood should feel futuristic, calm, and inspirational, suitable for a high-end AI product or cinematic workflow reveal. Clean mix, professional sound design, smooth transitions, no abrupt sounds."}],
                    "resultUrl": "Generate a cinematic ambient soundscape with deep atmospheric pads, soft evolving synth textures, subtle low-frequency pulses, and gentle high-end shimmer. The mood should feel futuristic, calm, and inspirational, suitable for a high-end AI product or cinematic workflow reveal. Clean mix, professional sound design, smooth transitions, no abrupt sounds."
                },
                "type": "textNode"
            },
            {
                "id": "audio1",
                "position": {"x": 400, "y": 100},
                "data": {
                    "selectedModel": {"id": "suno-create-music", "name": "Suno Create Music"},
                    "formValues": {"prompt": "Generate a cinematic ambient soundscape with deep atmospheric pads, soft evolving synth textures, subtle low-frequency pulses, and gentle high-end shimmer. The mood should feel futuristic, calm, and inspirational, suitable for a high-end AI product or cinematic workflow reveal. Clean mix, professional sound design, smooth transitions, no abrupt sounds.", "style": "Classical", "style_weight": 0, "vocal_gender": "male", "weirdness_constraint": 0, "audio_weight": 0, "instrumental": True, "model": "V5", "negative_tags": None},
                    "outputs": [{"type": "audio_url", "value": "https://cdn.muapi.ai/assets/demos/84827b58c95f49bc926024543f661b61.mp3"}],
                    "resultUrl": "https://cdn.muapi.ai/assets/demos/84827b58c95f49bc926024543f661b61.mp3"
                },
                "type": "audioNode"
            }
        ],
        "edges": [
            {"id": "e1-1", "source": "text1", "target": "audio1", "sourceHandle": "textOutput", "targetHandle": "audioInput2", "style": {"stroke": "#3b82f6", "strokeWidth": 2}}
        ]
    },
    {
        "preset_id": "captioning",
        "title": "LLM Image Captioning",
        "description": "Generate a prompt from an image with GPT-5",
        "icon": "text",
        "image": "https://cdn.muapi.ai/assets/demos/6a287f2ae6b849d5adca28fa0ea2cfd2.png",
        "category": "General",
        "sort_order": "4",
        "nodes": [
            {
                "id": "image1",
                "position": {"x": 0, "y": 100},
                "data": {
                    "selectedModel": {"id": "image-passthrough", "name": "Input Image"},
                    "formValues": {"image_url": "https://cdn.muapi.ai/assets/demos/6a287f2ae6b849d5adca28fa0ea2cfd2.png"},
                    "outputs": [{"type": "image_url", "value": "https://cdn.muapi.ai/assets/demos/6a287f2ae6b849d5adca28fa0ea2cfd2.png"}],
                    "resultUrl": "https://cdn.muapi.ai/assets/demos/6a287f2ae6b849d5adca28fa0ea2cfd2.png"
                },
                "type": "imageNode"
            },
            {
                "id": "text1",
                "position": {"x": 432, "y": -110},
                "data": {
                    "selectedModel": {"id": "gpt-5-nano", "name": "GPT5 Nano"},
                    "formValues": {"prompt": "Provide a detailed prompt of this image, capturing as many elements as possible. Include specifics about the colors, textures, any people or objects present, and the setting. Describe the atmosphere, any notable features or interactions, and the overall mood of the scene.", "image_url": "https://cdn.muapi.ai/assets/demos/6a287f2ae6b849d5adca28fa0ea2cfd2.png"},
                    "outputs": [{"type": "text", "value": "A cinematic sci‑fi cityscape at golden hour."}],
                    "resultUrl": "A cinematic sci‑fi cityscape at golden hour."
                },
                "type": "textNode"
            },
            {
                "id": "text2",
                "position": {"x": -2, "y": -335},
                "data": {
                    "selectedModel": {"id": "text-passthrough", "name": "Input Text"},
                    "formValues": {"prompt": "Provide a detailed prompt of this image, capturing as many elements as possible. Include specifics about the colors, textures, any people or objects present, and the setting. Describe the atmosphere, any notable features or interactions, and the overall mood of the scene."},
                    "outputs": [{"type": "text", "value": "Provide a detailed prompt of this image, capturing as many elements as possible. Include specifics about the colors, textures, any people or objects present, and the setting. Describe the atmosphere, any notable features or interactions, and the overall mood of the scene."}],
                    "resultUrl": "Provide a detailed prompt of this image, capturing as many elements as possible. Include specifics about the colors, textures, any people or objects present, and the setting. Describe the atmosphere, any notable features or interactions, and the overall mood of the scene."
                },
                "type": "textNode"
            }
        ],
        "edges": [
            {"id": "e4-1", "source": "image1", "target": "text1", "sourceHandle": "imageOutput", "targetHandle": "textInput2", "style": {"stroke": "#22c55e", "strokeWidth": 2}},
            {"id": "e4-2", "source": "text2", "target": "text1", "sourceHandle": "textOutput", "targetHandle": "textInput", "style": {"stroke": "#3b82f6", "strokeWidth": 2}}
        ]
    }
]


async def seed_workflow_presets(db: AsyncSession) -> int:
    """将预设模板写入数据库（已有则不覆盖）"""
    count = 0
    for preset_data in PRESET_SEED_DATA:
        existing = (await db.execute(
            sa_select(WorkflowPreset).where(WorkflowPreset.preset_id == preset_data["preset_id"])
        )).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(WorkflowPreset(
            preset_id=preset_data["preset_id"],
            title=preset_data["title"],
            description=preset_data["description"],
            icon=preset_data["icon"],
            image=preset_data["image"],
            category=preset_data["category"],
            nodes=preset_data["nodes"],
            edges=preset_data["edges"],
            sort_order=preset_data["sort_order"],
        ))
        count += 1
    if count:
        await db.flush()
        logger.info(f"[seed_workflow_presets] 新增 {count} 个预设模板")
    return count


async def get_workflow_presets(db: AsyncSession) -> list[dict]:
    """获取所有预设模板列表（摘要信息，不含 nodes/edges）"""
    result = await db.execute(
        sa_select(WorkflowPreset).order_by(WorkflowPreset.sort_order)
    )
    presets = result.scalars().all()
    return [
        {
            "id": p.preset_id,
            "title": p.title,
            "description": p.description,
            "icon": p.icon,
            "image": p.image,
            "category": p.category,
            "node_count": len(p.nodes or []),
            "edge_count": len(p.edges or []),
        }
        for p in presets
    ]


async def get_workflow_preset_detail(db: AsyncSession, preset_id: str) -> dict:
    """获取单个预设模板完整数据（含 nodes/edges）"""
    preset = (await db.execute(
        sa_select(WorkflowPreset).where(WorkflowPreset.preset_id == preset_id)
    )).scalar_one_or_none()
    if preset is None:
        raise HTTPException(status_code=404, detail=f"预设模板 {preset_id} 不存在")
    return {
        "id": preset.preset_id,
        "title": preset.title,
        "description": preset.description,
        "icon": preset.icon,
        "image": preset.image,
        "category": preset.category,
        "nodes": preset.nodes or [],
        "edges": preset.edges or [],
    }


async def update_workflow_preset(db: AsyncSession, preset_id: str, payload: dict) -> dict:
    """更新预设模板"""
    preset = (await db.execute(
        sa_select(WorkflowPreset).where(WorkflowPreset.preset_id == preset_id)
    )).scalar_one_or_none()
    if preset is None:
        raise HTTPException(status_code=404, detail=f"预设模板 {preset_id} 不存在")

    for field in ("title", "description", "icon", "image", "category", "nodes", "edges", "sort_order"):
        if field in payload:
            setattr(preset, field, payload[field])

    await db.flush()
    return {"ok": True, "preset_id": preset_id}
