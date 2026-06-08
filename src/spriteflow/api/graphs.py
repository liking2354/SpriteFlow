"""管线图 API — 保存/加载/执行 ComfyUI 风格节点图

端点：
    GET    /api/graphs                     列出所有图
    GET    /api/graphs/search?q=xxx        搜索图
    GET    /api/graphs/runs                 历史运行列表
    GET    /api/graphs/runs/{run_id}       查询执行状态
    GET    /api/graphs/runs/{run_id}/stream SSE 流式进度
    POST   /api/graphs/runs/{run_id}/rerun/{node_id}  单节点重跑
    GET    /api/graphs/{graph_id}          获取单个图
    POST   /api/graphs                     创建图
    PUT    /api/graphs/{graph_id}          更新图
    DELETE /api/graphs/{graph_id}          删除图
    POST   /api/graphs/run                 执行临时图（不保存）
    POST   /api/graphs/{graph_id}/run      执行已保存的图
"""

from __future__ import annotations

import json
import asyncio
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, Response, JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..graph.models import PipelineGraphModel
from ..graph.store import GraphStore
from ..graph.bridge import pipeline_graph_to_dag, validate_pipeline_graph
from ..engine.executor import RunStatus, NodeRunResult
from ..config import settings
from .deps import get_executor, get_db
from ..workflow.yaml_loader import WorkflowLoader

router = APIRouter()

# ── 单例 ──────────────────────────────────────────

_store = GraphStore()

# 运行记录（内存热缓存 + DB 持久化）
_runs: dict[str, Any] = {}  # run_id -> WorkflowRun
_run_graphs: dict[str, PipelineGraphModel] = {}  # run_id -> 执行时的图快照


# ── 请求模型 ──────────────────────────────────────

class GraphRunRequest(BaseModel):
    """执行管线图请求"""
    graph: PipelineGraphModel = Field(..., description="完整的管线图定义")


class GraphRunResponse(BaseModel):
    """执行管线图响应"""
    run_id: str
    graph_name: str
    status: str


# ── CRUD: 列出 / 搜索 ──────────────────────────────

@router.get("/graphs")
async def list_graphs(
    tag: str | None = None,
    limit: int = 20,
    offset: int = 0,
    q: str | None = None,
):
    """列出管线图（支持分页、搜索、标签过滤）

    Query params:
        tag:   按标签过滤
        q:     按名称/描述模糊搜索
        limit: 每页数量（默认 20，最大 100）
        offset: 偏移量（默认 0）
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    if q:
        entries = _store.search(q)
    else:
        entries = _store.list(tag=tag)

    total = len(entries)
    page = entries[offset:offset + limit]

    return {
        "graphs": [e.model_dump() for e in page],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/graphs/search")
async def search_graphs(q: str):
    """按名称/描述搜索管线图"""
    if not q or len(q) < 1:
        raise HTTPException(status_code=400, detail="搜索关键词不能为空")
    entries = _store.search(q)
    return {"graphs": [e.model_dump() for e in entries], "total": len(entries)}


# ── 预设管线图 ──────────────────────────────────────

_PRESETS_DIR = settings.project_root / "graphs" / "presets"
_RUNS_DIR = settings.project_root / "runs"  # 运行结果 JSON 持久化目录


@router.get("/graphs/presets")
async def list_presets():
    """列出所有预设管线图"""
    presets = []
    if _PRESETS_DIR.exists():
        for fp in sorted(_PRESETS_DIR.glob("*.json")):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                presets.append({
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "tags": data.get("tags", []),
                    "node_count": len(data.get("nodes", [])),
                    "edge_count": len(data.get("edges", [])),
                })
            except Exception:
                continue
    return {"presets": presets}


@router.get("/graphs/presets/{preset_id}")
async def get_preset(preset_id: str):
    """获取指定预设管线图完整 JSON"""
    if not _PRESETS_DIR.exists():
        raise HTTPException(status_code=404, detail="预设目录不存在")

    fp = _PRESETS_DIR / f"{preset_id}.json"
    if not fp.exists():
        # 也尝试直接匹配文件名
        for f in _PRESETS_DIR.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if data.get("id") == preset_id:
                    return data
            except Exception:
                continue
        raise HTTPException(status_code=404, detail=f"预设管线图不存在: {preset_id}")

    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"加载预设失败: {e}")


# ── 运行相关：必须在 /graphs/{graph_id} 之前注册 ───

@router.get("/graphs/runs")
async def list_graph_runs(limit: int = 20, graph_id: str | None = None):
    """列出历史运行记录（从 DB 查询）"""
    limit = max(1, min(limit, 100))

    try:
        db = get_db()
        if db._conn is not None:
            runs, total = await db.list_graph_runs(graph_id=graph_id, limit=limit, offset=0)
            records = []
            for r in runs:
                summary = None
                if r.summary_json:
                    try:
                        summary = json.loads(r.summary_json)
                    except Exception:
                        pass
                records.append({
                    "runId": r.id,
                    "graphId": r.graph_id,
                    "graphName": r.graph_name,
                    "status": r.status,
                    "startedAt": r.started_at,
                    "finishedAt": r.finished_at,
                    "summary": summary,
                })
            return {"runs": records, "total": total}
    except Exception:
        pass

    return {"runs": [], "total": 0}


@router.get("/graphs/runs/{run_id}")
async def get_run_status(run_id: str):
    """查询执行状态（内存 → DB）"""
    # 1. 内存（当前运行中）
    run = _runs.get(run_id)
    if run is not None:
        return {
            "runId": run.run_id,
            "graphName": run.workflow_name,
            "status": run.status.value,
            "startedAt": run.started_at,
            "finishedAt": run.finished_at,
            "results": {
                nid: {
                    "status": r.status.value,
                    "cacheHit": r.cache_hit,
                    "error": r.error,
                    "assetId": r.asset_id,
                    "url": _resolve_display_url(r.url) if r.url else None,
                    "nodeType": r.node_type if hasattr(r, "node_type") else "",
                    "inputs": r.inputs if hasattr(r, "inputs") and r.inputs else None,
                }
                for nid, r in run.results.items()
            },
        }

    # 2. DB（已持久化的运行记录）
    try:
        db = get_db()
        if db._conn is not None:
            db_run = await db.get_graph_run(run_id)
            if db_run is not None:
                node_results = await db.get_node_results(run_id)
                results = {}
                for nr in node_results:
                    results[nr.node_id] = {
                        "status": nr.status,
                        "cacheHit": nr.cache_hit,
                        "error": nr.error,
                        "assetId": nr.asset_id,
                        "url": _resolve_display_url(nr.url) if nr.url else None,
                        "nodeType": nr.node_type,
                        "inputs": _parse_inputs_json(nr.inputs_json),
                    }
                return {
                    "runId": db_run.id,
                    "graphName": db_run.graph_name,
                    "status": db_run.status,
                    "startedAt": db_run.started_at,
                    "finishedAt": db_run.finished_at,
                    "results": results,
                }
    except Exception:
        pass

    raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")


@router.get("/graphs/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    """SSE 端点：流式推送管线图执行进度

    事件类型:
      - run_started     {runId}
      - node_queued     {nodeId}
      - node_started    {nodeId}
      - node_completed  {nodeId, cacheHit, thumbnail, assetId, url}
      - node_failed     {nodeId, error}
      - run_completed   {runId, status, summary}
    """

    async def event_generator():
        # 等待 run 注册（后台异步执行可能需要几十毫秒）
        run = None
        for _ in range(20):  # 最多等 10 秒
            run = _runs.get(run_id)
            if run is not None:
                break
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.5)

        # 内存中没有 → 检查 DB（可能是服务重启后重连，或已完成的历史记录）
        if run is None:
            try:
                db = get_db()
                if db._conn is not None:
                    db_run = await db.get_graph_run(run_id)
                    if db_run is not None and db_run.status in ("completed", "failed"):
                        # 已完成：直接从 DB 重放最终状态
                        yield {
                            "event": "run_started",
                            "data": json.dumps({"runId": run_id, "graphName": db_run.graph_name, "status": "running"}),
                        }
                        node_results = await db.get_node_results(run_id)
                        for nr in node_results:
                            # 使用 model_dump(by_alias=True) 自动转换 Python snake_case → JSON camelCase
                            # display_url 已序列化为 "url"，thumbnail_b64 已序列化为 "thumbnail"
                            data = nr.model_dump(
                                by_alias=True,
                                include={"node_id", "cache_hit", "asset_id", "error", "display_url", "thumbnail_b64"},
                            )
                            data["nodeType"] = nr.node_type
                            parsed_inputs = _parse_inputs_json(nr.inputs_json)
                            if parsed_inputs:
                                data["inputs"] = parsed_inputs
                            yield {
                                "event": f"node_{nr.status}",
                                "data": json.dumps(data),
                            }
                        summary = None
                        if db_run.summary_json:
                            try:
                                summary = json.loads(db_run.summary_json)
                            except Exception:
                                pass
                        yield {
                            "event": "run_completed",
                            "data": json.dumps({
                                "runId": run_id,
                                "status": db_run.status,
                                "finishedAt": db_run.finished_at,
                                "summary": summary,
                            }),
                        }
                        return
            except Exception:
                pass

            yield {"event": "error", "data": json.dumps({"message": "运行记录不存在或已超时"})}
            return

        # 发送 run_started（用 placeholder 信息）
        yield {
            "event": "run_started",
            "data": json.dumps({"runId": run_id, "graphName": run.workflow_name, "status": "running"}),
        }

        # 每个节点已发射的状态集合 {node_id: set of emitted statuses}
        emitted: dict[str, set[str]] = {}

        # 轮询直到完成（所有节点不再有 PENDING/QUEUED/RUNNING 状态，
        # 且主 run 状态为 COMPLETED/FAILED — 兼容初始运行和 rerun 重跑场景）
        while True:
            if await request.is_disconnected():
                return

            # 每次轮询重新读取（因为后台任务可能替换了整个 run 对象）
            current_run = _runs.get(run_id)
            if current_run is not None:
                run = current_run

            has_active = False
            for nid, result in list(run.results.items()):
                if result.status in (RunStatus.PENDING, RunStatus.QUEUED, RunStatus.RUNNING):
                    has_active = True

                node_emitted = emitted.setdefault(nid, set())

                if result.status == RunStatus.QUEUED and "queued" not in node_emitted:
                    node_emitted.add("queued")
                    yield {
                        "event": "node_queued",
                        "data": json.dumps({"nodeId": nid}),
                    }
                elif result.status == RunStatus.RUNNING and "running" not in node_emitted:
                    node_emitted.add("running")
                    yield {
                        "event": "node_started",
                        "data": json.dumps({"nodeId": nid}),
                    }
                elif result.status == RunStatus.COMPLETED and "completed" not in node_emitted:
                    node_emitted.add("completed")
                    thumb = _make_thumbnail(result.outputs) if result.outputs else None
                    node_duration = _compute_node_duration(result)
                    yield {
                        "event": "node_completed",
                        "data": json.dumps({
                            "nodeId": nid,
                            "nodeType": result.node_type,
                            "cacheHit": result.cache_hit,
                            "duration": node_duration,
                            "thumbnail": thumb,
                            "assetId": result.asset_id,
                            "url": _resolve_display_url(result.url) if result.url else None,
                            "inputs": result.inputs if result.inputs else None,
                        }),
                    }
                elif result.status == RunStatus.FAILED and "failed" not in node_emitted:
                    node_emitted.add("failed")
                    yield {
                        "event": "node_failed",
                        "data": json.dumps({
                            "nodeId": nid,
                            "error": result.error,
                        }),
                    }

            # 退出条件：无活跃节点 且 主 run 已结束
            if not has_active and run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                break

            await asyncio.sleep(0.5)

        # 最终确认：再次刷新 run 引用（后台任务可能刚替换）
        final_run = _runs.get(run_id)
        if final_run is not None:
            run = final_run

        # 生成运行摘要并发送
        summary = _build_run_summary(run)
        yield {
            "event": "run_completed",
            "data": json.dumps({
                "runId": run_id,
                "status": run.status.value,
                "finishedAt": run.finished_at,
                "summary": summary,
            }),
        }

        # 短暂延迟确保客户端收到 run_completed 事件再关闭
        await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())


@router.post("/graphs/runs/{run_id}/rerun/{node_id}")
async def rerun_graph_node(run_id: str, node_id: str, mode: str = "node_and_downstream"):
    """重新运行指定节点（后台异步 + SSE 实时推送）

    mode 支持三种模式：
    - node_and_downstream: 目标节点 + 所有下游（默认）
    - node_only: 仅目标节点
    - downstream_only: 仅下游节点，不包括目标节点

    改动：改为后台 asyncio.create_task 执行，立即返回。
    前端需订阅 /graphs/runs/{run_id}/stream 获取实时进度。
    """
    run = _runs.get(run_id)
    graph = _run_graphs.get(run_id)

    if not run or not graph:
        raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")

    # 找到目标节点及其所有下游节点
    all_downstream = _find_downstream_nodes(graph, node_id)

    if not all_downstream:
        raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")

    # 根据 mode 筛选目标节点集合
    if mode == "node_only":
        target_nodes = {node_id}
    elif mode == "downstream_only":
        target_nodes = all_downstream - {node_id}
    else:
        target_nodes = all_downstream

    if not target_nodes:
        raise HTTPException(status_code=400, detail="目标节点集合为空")

    # 构建子图：包含目标节点及上游节点（用于 DAG 边解析输入依赖）
    # 上游节点会命中缓存跳过执行，上下文已预加载上游输出
    sub_node_ids = set(target_nodes)
    if mode == "node_only":
        sub_node_ids = _find_upstream_nodes(graph, node_id)
    elif mode == "downstream_only":
        # downstream_only 也需要上游节点来提供输入
        sub_node_ids = set(target_nodes)
        for nid in list(target_nodes):
            sub_node_ids |= _find_upstream_nodes(graph, nid)
    else:
        sub_node_ids = set(target_nodes)

    sub_nodes = [n for n in graph.nodes if n.id in sub_node_ids]
    sub_edges = [
        e for e in graph.edges
        if e.src_node in sub_node_ids and e.dst_node in sub_node_ids
    ]

    if not sub_nodes:
        raise HTTPException(status_code=400, detail="子图为空")

    sub_graph = PipelineGraphModel(
        schema_version=graph.schema_version,
        id=f"{graph.id}_rerun_{node_id}",
        name=f"{graph.name} (重跑 {node_id})",
        nodes=sub_nodes,
        edges=sub_edges,
    )

    try:
        dag, name, dag_errors = pipeline_graph_to_dag(sub_graph)
        if dag_errors:
            raise HTTPException(status_code=400, detail="; ".join(dag_errors))
        if dag is None:
            raise HTTPException(status_code=400, detail="子图 DAG 生成失败")

        errors = WorkflowLoader.validate(dag)
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 将目标节点状态重置为 PENDING（SSE 流可通过状态变化感知重跑进度）
    for nid in target_nodes:
        run.results[nid] = NodeRunResult(
            node_id=nid,
            status=RunStatus.PENDING,
            inputs={},
        )

    executor = get_executor()

    # 准备 context 预加载上游输出
    from ..engine.context import Context
    ctx = Context(
        cache=executor.cache,
        router=executor.router,
        storage=executor.storage,
        db=executor.db,
        template_db=executor.template_db,
    )
    for nid, result in run.results.items():
        if nid not in target_nodes and result.status == RunStatus.COMPLETED:
            ctx.set_node_output(nid, result.outputs)

    # 后台异步执行（与 _execute_graph 同模式）
    async def _bg_rerun():
        try:
            sub_run = await executor.execute(dag, workflow_name=name or "重跑")
            # 将子图执行结果合并回原 run
            for nid, result in sub_run.results.items():
                run.results[nid] = result
            # 持久化更新后的摘要
            try:
                _save_run_summary(run, graph)
            except Exception:
                pass
        except Exception as e:
            for nid in target_nodes:
                run.results[nid] = NodeRunResult(
                    node_id=nid,
                    status=RunStatus.FAILED,
                    error=str(e),
                    inputs={},
                )
            import logging
            logging.getLogger("spriteflow.graphs").error(f"节点重跑失败 [{run_id}/{node_id}]: {e}")

    asyncio.create_task(_bg_rerun())

    return {
        "runId": run_id,
        "nodeId": node_id,
        "rerunNodes": list(target_nodes),
        "status": "pending",
    }


@router.post("/graphs/{graph_id}/nodes/{node_id}/run")
async def run_single_node(graph_id: str, node_id: str):
    """冷启动执行单个节点（不需要先运行整图）

    提取指定节点为子图，创建新的运行记录，后台异步执行。
    前端需订阅 /graphs/runs/{run_id}/stream 获取实时进度。
    """
    graph = _store.load(graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"管线图不存在: {graph_id}")

    # 查找目标节点
    target_node = next((n for n in graph.nodes if n.id == node_id), None)
    if not target_node:
        raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")

    # 查找上游节点（BFS 向上追溯输入来源），构建完整子图
    # 上游节点会被 executor 从文件缓存命中并跳过执行
    upstream_node_ids = _find_upstream_nodes(graph, node_id)
    sub_nodes = [n for n in graph.nodes if n.id in upstream_node_ids]
    sub_edges = [
        e for e in graph.edges
        if e.src_node in upstream_node_ids and e.dst_node in upstream_node_ids
    ]

    sub_graph = PipelineGraphModel(
        schema_version=graph.schema_version,
        id=f"{graph.id}_single_{node_id}",
        name=f"{graph.name} (单节点 {node_id})",
        nodes=sub_nodes,
        edges=sub_edges,
    )

    # 校验
    try:
        dag, name, dag_errors = pipeline_graph_to_dag(sub_graph)
        if dag_errors:
            return JSONResponse(status_code=400, content={
                "message": "子图 DAG 生成失败",
                "validation_errors": dag_errors,
            })
        if dag is None:
            return JSONResponse(status_code=400, content={"message": "子图 DAG 为空"})

        errors = WorkflowLoader.validate(dag)
        if errors:
            return JSONResponse(status_code=400, content={
                "message": "节点校验失败",
                "validation_errors": errors,
            })
    except ValueError as e:
        return JSONResponse(status_code=400, content={"message": str(e)})

    import logging
    import uuid

    executor = get_executor()
    run_id = f"grun_{uuid.uuid4().hex[:12]}"

    # 创建占位 run 并注册到内存
    from ..engine.executor import WorkflowRun, RunStatus
    placeholder = WorkflowRun(
        run_id=run_id,
        status=RunStatus.PENDING,
        workflow_name=name or "单节点执行",
    )
    _runs[run_id] = placeholder
    _run_graphs[run_id] = graph  # 保存原始图快照（用于 rerun 等）

    # 同步写入 DB 占位
    try:
        db = get_db()
        if db._conn is not None:
            from ..asset_hub.models import GraphRun as DbGraphRun
            db_run = DbGraphRun(
                id=run_id,
                graph_id=graph.id,
                graph_name=name or "单节点执行",
                graph_json=graph.model_dump_json(exclude_none=False),
                status="pending",
                started_at=datetime.now().isoformat(),
                created_at=datetime.now().isoformat(),
            )
            await db.create_graph_run(db_run)
            logging.getLogger("spriteflow.graphs").info(f"单节点运行占位记录已写入 DB: {run_id}")
    except Exception as e:
        logging.getLogger("spriteflow.graphs").error(f"写入单节点运行占位失败 [{run_id}]: {e}")

    # 后台异步执行
    async def _bg_single_node():
        try:
            sub_run = await executor.execute(dag, run=placeholder, run_id=run_id, workflow_name=name or "单节点执行")
            _runs[run_id] = sub_run
            # 持久化
            await _persist_run_to_db(run_id, sub_run, graph)
            _save_run_summary(sub_run, graph)
        except Exception as e:
            placeholder.status = RunStatus.FAILED
            placeholder.finished_at = datetime.now().isoformat()
            logging.getLogger("spriteflow.graphs").error(f"单节点执行失败 [{run_id}/{node_id}]: {e}")
            try:
                await _persist_run_to_db(run_id, placeholder, graph)
            except Exception:
                pass

    asyncio.create_task(_bg_single_node())

    return {
        "runId": run_id,
        "graphId": graph_id,
        "nodeId": node_id,
        "status": "pending",
    }


def _find_downstream_nodes(graph: PipelineGraphModel, node_id: str) -> set[str]:
    """BFS 查找目标节点及其所有下游节点"""
    if not any(n.id == node_id for n in graph.nodes):
        return set()

    downstream: dict[str, set[str]] = {}
    for e in graph.edges:
        downstream.setdefault(e.src_node, set()).add(e.dst_node)

    visited: set[str] = set()
    queue = [node_id]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for child in downstream.get(current, set()):
            if child not in visited:
                queue.append(child)

    return visited


def _find_upstream_nodes(graph: PipelineGraphModel, node_id: str) -> set[str]:
    """BFS 查找目标节点及其所有上游（输入来源）节点"""
    if not any(n.id == node_id for n in graph.nodes):
        return set()

    # 反向邻接表: dst → {src ...}
    upstream: dict[str, set[str]] = {}
    for e in graph.edges:
        upstream.setdefault(e.dst_node, set()).add(e.src_node)

    visited: set[str] = set()
    queue = [node_id]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for parent in upstream.get(current, set()):
            if parent not in visited:
                queue.append(parent)

    return visited


# ── 图片代理（必须在 /graphs/{graph_id} 之前注册，避免被当作 graph_id）──

@router.get("/graphs/image-proxy")
async def image_proxy(uri: str = Query(..., description="存储 URI")):
    """代理存储图片：将 cos:// 或 local:// URI 转为 HTTP 响应"""
    from .deps import get_storage
    import io
    from PIL import Image

    storage = get_storage()
    try:
        data = await storage.download(uri)
        # 检测图片格式
        try:
            img = Image.open(io.BytesIO(data))
            fmt = img.format or "PNG"
        except Exception:
            fmt = "PNG"
        content_type = f"image/{fmt.lower()}"
        return Response(content=data, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"图片加载失败: {e}")


# ── 查看最近一次运行结果（必须在 /graphs/{graph_id} 之前注册）───

@router.get("/graphs/{graph_id}/latest-run-results")
async def get_graph_latest_run_results(graph_id: str):
    """获取指定管线图的最近一次运行结果（用于页面重进时恢复展示状态）"""
    try:
        db = get_db()
        if db._conn is None:
            return {"runId": None, "status": None, "nodeResults": {}}

        # 查找最近一次运行
        runs, total = await db.list_graph_runs(graph_id=graph_id, limit=1, offset=0)
        if total == 0 or not runs:
            return {"runId": None, "status": None, "nodeResults": {}}

        latest_run = runs[0]
        node_results = await db.get_node_results(latest_run.id)

        # 没有实际结果（如 pending 状态）则不返回
        if not node_results:
            return {"runId": None, "status": None, "nodeResults": {}}

        results: dict[str, dict[str, Any]] = {}
        for nr in node_results:
            data = nr.model_dump(by_alias=True, include={"status", "cache_hit", "error", "asset_id", "display_url", "thumbnail_b64"})
            data["nodeType"] = nr.node_type
            parsed_inputs = _parse_inputs_json(nr.inputs_json)
            if parsed_inputs:
                data["inputs"] = parsed_inputs
            results[nr.node_id] = data

        return {
            "runId": latest_run.id,
            "status": latest_run.status,
            "finishedAt": latest_run.finished_at,
            "nodeResults": results,
        }
    except Exception:
        return {"runId": None, "status": None, "nodeResults": {}}


# ── CRUD: 单个图操作（必须在 /graphs/runs/* 之后注册）───

@router.get("/graphs/{graph_id}")
async def get_graph(graph_id: str):
    """获取单个管线图"""
    graph = _store.load(graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"管线图不存在: {graph_id}")
    return graph.model_dump()


@router.post("/graphs")
async def create_graph(graph: PipelineGraphModel):
    """创建管线图"""
    try:
        saved = _store.save(graph)
        return saved.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"保存失败: {e}")


@router.put("/graphs/{graph_id}")
async def update_graph(graph_id: str, graph: PipelineGraphModel):
    """更新管线图"""
    existing = _store.load(graph_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"管线图不存在: {graph_id}")

    # 保持 ID 不变
    graph.id = graph_id
    try:
        saved = _store.save(graph)
        return saved.model_dump()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"更新失败: {e}")


@router.delete("/graphs/{graph_id}")
async def delete_graph(graph_id: str):
    """删除管线图"""
    ok = _store.delete(graph_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"管线图不存在: {graph_id}")
    return {"status": "deleted", "id": graph_id}


# ── 执行 ─────────────────────────────────────────

@router.post("/graphs/run")
async def run_graph(body: GraphRunRequest):
    """执行临时管线图（不要求先保存）"""
    graph = body.graph
    return await _execute_graph(graph)


@router.post("/graphs/{graph_id}/run")
async def run_saved_graph(graph_id: str):
    """执行已保存的管线图"""
    graph = _store.load(graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail=f"管线图不存在: {graph_id}")
    return await _execute_graph(graph)


async def _execute_graph(graph: PipelineGraphModel) -> dict:
    """核心执行逻辑：校验 → 启动后台执行 → 立即返回 run_id

    Returns:
        dict: {
            "runId": str,
            "graphName": str,
            "status": str,
            "validation_errors": [...] | None,
        } 或直接 raise HTTPException

    改动说明：
    - 校验同步完成（失败返回结构化 per-node 错误，前端可定位到具体节点）
    - 通过 executor.execute 返回的 WorkflowRun 预先拿到 run_id
    - 后台 asyncio.create_task 执行管线图
    - SSE 端点通过轮询 _runs[run_id] 获取实时进度
    """
    # 同步校验（失败返回结构化错误）
    try:
        validation_errors = validate_pipeline_graph(graph)
        if validation_errors:
            node_errors = _parse_validation_errors(validation_errors)
            return JSONResponse(
                status_code=400,
                content={
                    "message": "管线图校验失败",
                    "validation_errors": validation_errors,
                    "node_errors": node_errors,
                },
            )

        dag, name, dag_errors = pipeline_graph_to_dag(graph)
        if dag_errors:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "DAG 生成失败",
                    "validation_errors": dag_errors,
                    "node_errors": _parse_validation_errors(dag_errors),
                },
            )
        if dag is None:
            return JSONResponse(
                status_code=400,
                content={"message": "DAG 生成失败：返回空 DAG"},
            )

        errors = WorkflowLoader.validate(dag)
        if errors:
            return JSONResponse(
                status_code=400,
                content={
                    "message": "DAG 结构校验失败",
                    "validation_errors": errors,
                },
            )

    except ValueError as e:
        return JSONResponse(status_code=400, content={"message": str(e)})

    # 创建占位 run 记录并立即注册（确保 SSE 能找到）
    executor = get_executor()
    from ..engine.executor import WorkflowRun, RunStatus

    run_id = f"grun_{uuid.uuid4().hex[:12]}"
    placeholder = WorkflowRun(
        run_id=run_id,
        status=RunStatus.PENDING,
        workflow_name=name or "管线图",
    )
    _runs[run_id] = placeholder
    _run_graphs[run_id] = graph

    # 同步写入 DB 占位记录（确保 SSE 能从 DB 恢复）
    import logging
    try:
        db = get_db()
        if db._conn is not None:
            from ..asset_hub.models import GraphRun as DbGraphRun
            db_run = DbGraphRun(
                id=run_id,
                graph_id=graph.id,
                graph_name=name or "管线图",
                graph_json=graph.model_dump_json(exclude_none=False),
                status="pending",
                started_at=datetime.now().isoformat(),
                created_at=datetime.now().isoformat(),
            )
            await db.create_graph_run(db_run)
            logging.getLogger("spriteflow.graphs").info(f"运行占位记录已写入 DB: {run_id} (graph={graph.id})")
    except Exception as e:
        logging.getLogger("spriteflow.graphs").error(
            f"写入运行占位记录失败 [{run_id} / graph={graph.id}]: {e}"
        )

    # 后台异步执行管线图
    async def _bg_execute():
        try:
            run = await executor.execute(dag, run=placeholder, run_id=run_id, workflow_name=name or "管线图")
            _runs[run_id] = run  # 替换占位（run 即 placeholder，此处为安全赋值）

            # 持久化运行结果到 DB
            await _persist_run_to_db(run_id, run, graph)
        except Exception as e:
            placeholder.status = RunStatus.FAILED
            placeholder.finished_at = datetime.now().isoformat()
            import logging
            logging.getLogger("spriteflow.graphs").error(f"管线图执行失败 [{run_id}]: {e}")

            # 持久化失败状态到 DB
            try:
                await _persist_run_to_db(run_id, placeholder, graph)
            except Exception as pe:
                logging.getLogger("spriteflow.graphs").exception(
                    f"持久化失败状态到 DB 也失败 [{run_id}]: {pe}"
                )

    asyncio.create_task(_bg_execute())

    return {
        "runId": run_id,
        "graphName": name or "管线图",
        "status": "pending",
    }


# ── 工具函数 ──────────────────────────────────────

def _parse_validation_errors(errors: list[str]) -> dict[str, list[str]]:
    """将 [node_id] 格式的校验错误解析为 {node_id: [error1, error2], ...} 映射

    前端可通过此结构高亮特定节点并展示其错误信息。
    """
    node_errors: dict[str, list[str]] = {}
    for error in errors:
        if error.startswith("[") and "]" in error:
            bracket_end = error.index("]")
            node_id = error[1:bracket_end]
            message = error[bracket_end + 1:].strip()
            node_errors.setdefault(node_id, []).append(message)
        else:
            node_errors.setdefault("_global", []).append(error)
    return node_errors


def _parse_inputs_json(inputs_json: str | None) -> dict | None:
    """将 inputs_json 字符串解析为 dict"""
    if not inputs_json:
        return None
    try:
        return json.loads(inputs_json)
    except Exception:
        return None


def _resolve_display_url(uri: str | None) -> str | None:
    """将存储 URI 转为前端可用的 HTTP URL

    cos://bucket/key → /api/graphs/image-proxy?uri=cos://bucket/key
    local://path → /api/graphs/image-proxy?uri=local://path
    HTTP(S) URL 直接返回
    """
    if not uri:
        return None
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    from urllib.parse import quote
    return f"/api/graphs/image-proxy?uri={quote(uri, safe='')}"


def _make_thumbnail(outputs: dict) -> str | None:
    """从节点输出中提取 base64 缩略图（支持单图或图列表）"""
    import base64, io
    from PIL import Image

    for value in outputs.values():
        if isinstance(value, Image.Image):
            thumb = value.copy()
            thumb.thumbnail((128, 128), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            thumb.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Image.Image):
                    thumb = item.copy()
                    thumb.thumbnail((128, 128), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    thumb.save(buf, format="PNG")
                    return base64.b64encode(buf.getvalue()).decode("utf-8")
    return None


def _compute_node_duration(result: Any) -> float | None:
    """从 NodeRunResult 计算节点执行耗时（秒）"""
    if result.started_at and result.finished_at:
        try:
            from datetime import datetime
            start = datetime.fromisoformat(result.started_at)
            end = datetime.fromisoformat(result.finished_at)
            return round((end - start).total_seconds(), 2)
        except (ValueError, TypeError):
            pass
    return None


def _build_run_summary(run: Any) -> dict:
    """构建运行摘要"""
    from datetime import datetime

    success_nodes = []
    failed_nodes = []
    cache_hits = 0
    assets: list[dict] = []

    for nid, result in run.results.items():
        if result.status == RunStatus.COMPLETED:
            success_nodes.append({
                "nodeId": nid,
                "cacheHit": result.cache_hit,
                "assetId": result.asset_id,
                "url": result.url,
            })
            if result.cache_hit:
                cache_hits += 1
            if result.asset_id:
                assets.append({
                    "nodeId": nid,
                    "assetId": result.asset_id,
                    "url": result.url,
                })
        elif result.status == RunStatus.FAILED:
            failed_nodes.append({
                "nodeId": nid,
                "error": result.error,
            })

    duration = 0.0
    if run.started_at and run.finished_at:
        try:
            start = datetime.fromisoformat(run.started_at)
            end = datetime.fromisoformat(run.finished_at)
            duration = (end - start).total_seconds()
        except (ValueError, TypeError):
            pass

    return {
        "duration": round(duration, 2),
        "successCount": len(success_nodes),
        "failedCount": len(failed_nodes),
        "cacheHits": cache_hits,
        "assets": assets,
        "failedNodes": failed_nodes,
    }


def _save_run_summary(run: Any, graph: PipelineGraphModel) -> None:
    """持久化运行记录到 JSON 文件"""
    runs_dir = _RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)

    summary = _build_run_summary(run)
    record = {
        "runId": run.run_id,
        "graphId": graph.id,
        "graphName": run.workflow_name,
        "status": run.status.value,
        "startedAt": run.started_at,
        "finishedAt": run.finished_at,
        "summary": summary,
        "nodeResults": {
            nid: {
                "status": r.status.value,
                "cacheHit": r.cache_hit,
                "error": r.error,
                "assetId": r.asset_id,
                "url": r.url,
                "startedAt": r.started_at,
                "finishedAt": r.finished_at,
                "thumbnail": _make_thumbnail(r.outputs) if r.outputs else None,
                "nodeType": r.node_type if hasattr(r, "node_type") else "",
                "inputs": r.inputs if hasattr(r, "inputs") and r.inputs else None,
            }
            for nid, r in run.results.items()
        },
    }

    filepath = runs_dir / f"{run.run_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False, default=str)


def _load_run_json(run_id: str) -> dict | None:
    """从持久化 JSON 文件加载运行记录"""
    filepath = _RUNS_DIR / f"{run_id}.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


async def _persist_run_to_db(run_id: str, run: Any, graph: PipelineGraphModel) -> None:
    """将运行结果持久化到 SQLite（含每个节点的缩略图）

    使用 INSERT OR REPLACE 确保即使占位记录创建失败也能写入完整记录。
    json 文件由 _save_run_summary 并行写入，作为备份。
    """
    from ..asset_hub.models import GraphRun as DbGraphRun, GraphNodeResult
    from datetime import datetime as dt
    import logging

    try:
        db = get_db()
        if db._conn is None:
            logging.getLogger("spriteflow.graphs").warning("DB 连接不可用，跳过持久化")
            return

        summary = _build_run_summary(run)
        status_str = run.status.value if hasattr(run.status, "value") else str(run.status)

        # 使用 INSERT OR REPLACE 确保记录一定存在（即使 create_graph_run 失败了）
        await db._conn.execute(
            """INSERT OR REPLACE INTO graph_runs
               (id, graph_id, graph_name, graph_json, status,
                started_at, finished_at, summary_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                   (SELECT created_at FROM graph_runs WHERE id = ?),
                   ?
               ))""",
            (
                run_id, graph.id, graph.name or "管线图",
                graph.model_dump_json(exclude_none=False),
                status_str, getattr(run, "started_at", "") or "",
                run.finished_at,
                json.dumps(summary, ensure_ascii=False, default=str),
                run_id,  # for COALESCE subquery
                datetime.now().isoformat(),  # fallback created_at
            ),
        )
        await db._conn.commit()
        logging.getLogger("spriteflow.graphs").info(
            f"运行记录已持久化: {run_id} (graph={graph.id}, status={status_str})"
        )

        # 逐节点写入结果
        for nid, r in run.results.items():
            thumb_b64 = _make_thumbnail(r.outputs) if r.outputs else None
            nr = GraphNodeResult(
                run_id=run_id,
                node_id=nid,
                status=r.status.value if hasattr(r.status, "value") else str(r.status),
                cache_hit=bool(r.cache_hit),
                error=r.error,
                asset_id=r.asset_id,
                url=r.url,
                display_url=_resolve_display_url(r.url) if r.url else None,
                thumbnail_b64=thumb_b64,
                started_at=r.started_at or "",
                finished_at=r.finished_at or "",
                node_type=getattr(r, "node_type", "") or "",
                inputs_json=json.dumps(r.inputs, ensure_ascii=False, default=str) if r.inputs else None,
            )
            await db.upsert_node_result(nr)
        logging.getLogger("spriteflow.graphs").info(
            f"节点结果已持久化: {run_id} ({len(run.results)} nodes)"
        )
    except Exception:
        logging.getLogger("spriteflow.graphs").exception(
            f"持久化运行记录到 DB 失败 [{run_id}]"
        )
