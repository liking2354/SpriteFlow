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
import traceback
import httpx
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import select, delete, update, text, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from sqlalchemy import select as sa_select
from .models import Workflow, RunHistory, RunHistoryArchive, ModelConfig, WorkflowPreset, gen_uuid
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

    # 合并：边缘连线的值覆盖 input_params 中的旧值（全部运行时上游已产生新输出）
    merged = dict(input_params)
    merge_count = 0
    for key, val in injected.items():
        # 边缘值始终覆盖（视觉化编程预期行为：连线代表数据流，应优先于缓存的旧值）
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


async def _refresh_cos_urls(params: dict[str, Any]) -> dict[str, Any]:
    """清理 input_params 中 COS URL 的过期签名查询参数，并将本地 URL / 文件路径上传到 COS。

    桶配置为公有读后，去掉 ?q-sign-* 参数即可直接访问，
    不再需要预签名 URL，也不暴露 SecretId。
    本地 URL（http://127.0.0.1:.../api/workflow/runs/...）和本地文件路径（/tmp/...）
    对外部 API 不可访问，需要先上传到 COS 获取公网 URL。

    支持字段：
    - 单值字段：image_url, image, video_url, audio_url, last_image
    - 数组字段：images_list（图片 URL 列表）
    """
    from urllib.parse import urlparse, urlunparse
    from ..components.utils import is_local_file_path, upload_file_to_cos

    url_keys = ["image_url", "image", "video_url", "audio_url", "last_image"]
    refreshed = dict(params)

    async def _process_single_url(key: str, url: str) -> str | None:
        """处理单个 URL，返回替换后的 URL（无需替换则返回 None）。"""
        # 本地文件路径（组件 save_image_local 返回）→ 上传到 COS
        if is_local_file_path(url):
            try:
                cos_url = await upload_file_to_cos(url)
                if cos_url:
                    logger.info(
                        "[workflow] uploaded local file→COS for key=%s → %s",
                        key, cos_url[:120],
                    )
                    return cos_url
            except Exception as e:
                logger.error("[workflow] failed to upload local file→COS for key=%s: %s", key, e)
            return None

        # 本地 workflow runs URL → 上传到 COS
        if "/api/workflow/runs/" in url and "127.0.0.1" in url:
            try:
                cos_url = await _upload_local_to_cos(url)
                if cos_url:
                    logger.info(
                        "[workflow] uploaded local→COS for key=%s → %s",
                        key, cos_url[:120],
                    )
                    return cos_url
            except Exception as e:
                logger.error("[workflow] failed to upload local→COS for key=%s: %s", key, e)
            return None

        # 清理 COS 签名参数
        if url.startswith(_COS_BASE_URL):
            parsed = urlparse(url)
            if parsed.query:
                clean_url = urlunparse(parsed._replace(query=""))
                logger.info(
                    "[workflow] stripped COS signature for key=%s → %s",
                    key, clean_url[:120],
                )
                return clean_url

        return None

    # 处理单值字段
    for key in url_keys:
        url = refreshed.get(key)
        if not isinstance(url, str) or not url:
            continue
        new_url = await _process_single_url(key, url)
        if new_url:
            refreshed[key] = new_url

    # 处理 images_list 数组字段
    images_list = refreshed.get("images_list")
    if isinstance(images_list, list) and images_list:
        new_list = []
        for idx, item in enumerate(images_list):
            if isinstance(item, str) and item:
                new_url = await _process_single_url(f"images_list[{idx}]", item)
                new_list.append(new_url if new_url else item)
            else:
                new_list.append(item)
        refreshed["images_list"] = new_list
        logger.info(
            "[workflow] refreshed images_list: %d items", len(new_list)
        )

    return refreshed


async def _upload_local_to_cos(local_url: str) -> str | None:
    """将本地 workflow runs 文件上传到 COS，返回公网 URL。"""
    import re
    from ..config import settings

    m = re.search(r"/api/workflow/runs/([^/]+)/outputs/(.+)", local_url)
    if not m:
        return None

    run_id, filename = m.group(1), m.group(2)
    filepath = settings.workflow_runs_dir / run_id / "outputs" / filename
    if not filepath.is_file():
        logger.error("[workflow] local file not found: %s", filepath)
        return None

    data = filepath.read_bytes()

    from spriteflow.api.deps import get_storage
    from spriteflow.storage.base import StoragePrefix

    storage = get_storage()
    uri = await storage.upload(filename, data, prefix=StoragePrefix.AI_PROCESSED, content_type="image/png")

    try:
        url = await storage.get_presigned_url(uri)
    except Exception:
        url = uri

    return url

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

    # 查询最近一次全工作流运行的 run_id（如果仍有节点在 running，前端需要恢复轮询）
    # 按节点数分组，优先返回节点数最多的运行（全工作流运行），
    # 节点数相同时取最新的（避免单节点手动运行覆盖全工作流运行的结果）
    run_id = None
    result = await db.execute(
        select(RunHistory.run_id, sa_func.count(RunHistory.id).label("node_count"))
        .where(RunHistory.workflow_id == workflow_id)
        .group_by(RunHistory.run_id)
        .order_by(sa_func.count(RunHistory.id).desc(), sa_func.max(RunHistory.created_at).desc())
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

    # 删除关联的运行历史（活跃表 + 归档表）
    await db.execute(
        text("DELETE FROM workflow_run_history WHERE workflow_id = :wfid"),
        {"wfid": workflow_id},
    )
    await db.execute(
        text("DELETE FROM workflow_run_history_archive WHERE workflow_id = :wfid"),
        {"wfid": workflow_id},
    )
    await db.delete(wf)
    await db.flush()
    return {"detail": "Workflow deleted successfully"}


async def duplicate_workflow_helper(db: AsyncSession, workflow_id: str, payload: dict | None = None) -> dict:
    """
    POST /api/workflow/{id}/duplicate
    复制工作流 — 创建完整副本（nodes、edges、category），命名为「原名称 (Copy)」
    """
    wf = await _get_workflow(db, workflow_id)
    new_name = (payload or {}).get("name") or f"{wf.name} (Copy)"
    new_wf = Workflow(
        id=gen_uuid(),
        name=new_name,
        data=wf.data,
        edges=wf.edges,
        category=wf.category,
        thumbnail=wf.thumbnail,
    )
    db.add(new_wf)
    await db.flush()
    logger.info("[duplicate_workflow] %s → %s (%s)", workflow_id, new_wf.id, new_name)
    return {"workflow_id": new_wf.id, "name": new_wf.name}


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

    每次「全部运行」视为一次全新任务：
    1. 将当前 RunHistory 中的旧记录移入 RunHistoryArchive 历史表
    2. 清空 RunHistory 中该工作流的活跃记录
    3. 创建全新的 run_id + 节点记录
    """
    wf = await _get_workflow(db, workflow_id)

    # ── 第一步：归档旧运行记录 ──
    existing = await db.execute(
        select(RunHistory).where(RunHistory.workflow_id == workflow_id)
    )
    existing_rows = existing.scalars().all()
    for row in existing_rows:
        archive = RunHistoryArchive(
            id=gen_uuid(),
            workflow_id=row.workflow_id,
            node_id=row.node_id,
            run_id=row.run_id,
            node_run_id=row.node_run_id,
            status=row.status,
            node_data=row.node_data,
            result=row.result,
        )
        db.add(archive)

    # ── 第二步：清空活跃记录 ──
    await db.execute(
        text("DELETE FROM workflow_run_history WHERE workflow_id = :wfid"),
        {"wfid": workflow_id},
    )

    # ── 第三步：创建全新运行记录 ──
    run_id = gen_uuid()
    nodes_data = wf.data.get("nodes", []) if isinstance(wf.data, dict) else []

    for node in nodes_data:
        node_id = node.get("id", "")
        node_run = RunHistory(
            id=gen_uuid(),
            workflow_id=workflow_id,
            node_id=node_id,
            run_id=run_id,
            node_run_id=gen_uuid(),
            status="pending",  # 初始为 pending，实际执行时由 execute_workflow_run 改为 running
            node_data=node,
        )
        db.add(node_run)

    await db.flush()
    await db.commit()  # 必须提交，否则后台任务会遇到 SQLite 数据库锁
    edges = wf.edges or []
    return {"run_id": run_id, "nodes_data": nodes_data, "workflow_id": workflow_id, "edges": edges}


def _topological_sort(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """根据 edges 对 nodes 做拓扑排序，保证上游节点先于下游节点执行

    Args:
        nodes: 节点数据列表，每个含 "id" 字段
        edges: 边列表，每个含 "source" 和 "target" 字段

    Returns:
        拓扑排序后的节点列表；如果存在环，返回原顺序
    """
    if not edges:
        return list(nodes)

    node_map = {n["id"]: n for n in nodes}
    node_ids = set(node_map.keys())

    # 构建邻接表和入度
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in node_ids and tgt in node_ids:
            adj[src].append(tgt)
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

    # Kahn 算法
    from collections import deque
    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    sorted_ids: list[str] = []

    while queue:
        nid = queue.popleft()
        sorted_ids.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # 如果排序后数量不一致（有环），退回原顺序
    if len(sorted_ids) != len(node_ids):
        logger.warning(
            "[workflow] cycle detected in edges, falling back to original node order"
        )
        return list(nodes)

    # 未在 edges 中出现的孤立节点追加到末尾
    remaining = node_ids - set(sorted_ids)
    sorted_ids.extend(remaining)

    return [node_map[nid] for nid in sorted_ids if nid in node_map]


async def _save_outputs_to_local(
    result: dict[str, Any],
    run_id: str,
    node_id: str,
) -> dict[str, Any]:
    """将工作流节点输出的图片保存到本地持久化目录。

    支持两种输入格式：
    1. 本地文件路径（组件 save_image_local 返回的 /tmp/... 路径）→ 直接复制
    2. 远程 URL（COS / 外部 URL）→ HTTP 下载

    每次全部运行触发后，以 run_id 创建独立目录存放此次生成的所有文件。

    目录结构：
        data/runs/{run_id}/
        ├── outputs/           ← 各节点输出的图片
        │   ├── {node_id}_0.png
        │   ├── {node_id}_1.png
        │   └── ...
    """
    outputs = result.get("outputs", [])
    if not outputs:
        return result

    from ..config import settings
    from ..components.utils import is_local_file_path

    run_dir = settings.workflow_runs_dir / run_id / "outputs"
    run_dir.mkdir(parents=True, exist_ok=True)

    modified = False
    new_outputs: list[dict[str, Any]] = []

    for idx, out in enumerate(outputs):
        if out.get("type") == "image_url" and out.get("value"):
            url = out["value"]
            # 已经是本地服务 URL 则跳过
            if "/api/workflow/runs/" in url:
                new_outputs.append(out)
                continue
            try:
                # 本地文件名：{node_id}_{index}.png
                filename = f"{node_id}_{idx}.png"
                filepath = run_dir / filename

                # 判断是本地文件路径还是远程 URL
                if is_local_file_path(url):
                    # 本地文件路径（组件 save_image_local 返回）→ 直接复制
                    import shutil
                    shutil.copy2(url, filepath)
                    image_data = filepath.read_bytes()
                else:
                    # 远程 URL → HTTP 下载
                    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                        resp = await client.get(url, follow_redirects=True)
                        resp.raise_for_status()
                        image_data = resp.content
                    filepath.write_bytes(image_data)

                # 本地持久化 HTTP URL（前端 + 下游节点均通过该 URL 加载图片）
                local_url = f"{settings.local_base_url}/api/workflow/runs/{run_id}/outputs/{filename}"

                # 读取图片尺寸
                from PIL import Image
                import io as pil_io
                try:
                    img = Image.open(pil_io.BytesIO(image_data))
                    w, h = img.size
                except Exception:
                    w, h = out.get("width"), out.get("height")

                new_outputs.append({
                    "type": "image_url",
                    "value": local_url,
                    "width": w,
                    "height": h,
                })
                modified = True
                logger.info(
                    "[workflow] saved locally: %s (%dx%d) node=%s",
                    filename, w or 0, h or 0, node_id,
                )
            except Exception as e:
                logger.error(
                    "[workflow] failed to save local image (node=%s idx=%d): %s",
                    node_id, idx, e,
                )
                new_outputs.append(out)  # 保留原输出，不阻塞流程
        else:
            new_outputs.append(out)

    if modified:
        result = {**result, "outputs": new_outputs}

    return result


async def execute_workflow_run(
    run_id: str,
    workflow_id: str,
    nodes_data: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    resume_from: str | None = None,
) -> None:
    """
    后台异步执行工作流所有节点。

    使用独立的数据库会话，按拓扑顺序逐个执行节点（上游先执行，
    确保边引用能正确解析），每次执行前后更新 RunHistory 状态。
    前端通过 GET /api/workflow/run/{run_id}/status 轮询状态变化。

    Args:
        resume_from: 如果提供，则从该节点开始执行（恢复模式）。
                     该节点之前的已成功节点跳过执行，但其输出从 DB 恢复到内存中
                     供下游节点解析边引用。
    """
    from .database import async_session as _async_session

    # 拓扑排序：确保上游节点先于下游节点执行
    sorted_nodes = _topological_sort(nodes_data, edges or [])
    if len(sorted_nodes) != len(nodes_data):
        logger.warning(
            "[workflow] topological sort mismatch: %d nodes → %d sorted, "
            "falling back to original order",
            len(nodes_data), len(sorted_nodes),
        )
        sorted_nodes = nodes_data

    # 创建本次运行的本地持久化目录
    from ..config import settings
    run_output_dir = settings.workflow_runs_dir / run_id / "outputs"
    run_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("[workflow] run output dir: %s", run_output_dir)

    # 维护已执行节点的输出，用于解析下游节点的边缘引用
    node_outputs: dict[str, list[dict[str, Any]]] = {}
    # 维护已执行节点的完整结果（含 meta），供下游读取 all_urls 等元数据
    node_results: dict[str, dict[str, Any]] = {}

    # ── 恢复模式：从 DB 加载已成功节点的输出 ──
    if resume_from:
        logger.info("[workflow] resume mode: starting from node=%s", resume_from)
        # 从 DB 读取当前 run 中所有节点的状态和结果
        async with _async_session() as resume_db:
            rows = await resume_db.execute(
                text(
                    "SELECT node_id, status, result FROM workflow_run_history "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
            for row in rows.fetchall():
                nid, nstatus, nresult = row
                if nstatus == "succeeded" and nresult:
                    try:
                        rj = json.loads(nresult) if isinstance(nresult, str) else nresult
                        outputs_list = rj.get("outputs", [])
                        if outputs_list:
                            node_outputs[nid] = outputs_list
                        node_results[nid] = rj
                    except Exception:
                        pass

        # 找到 resume_from 在拓扑排序中的位置，跳过之前的节点
        resume_idx = None
        for i, n in enumerate(sorted_nodes):
            if n.get("id") == resume_from:
                resume_idx = i
                break

        if resume_idx is not None:
            # 将 resume_from 及其之后的非成功节点状态重置为 pending
            # 已成功的节点保持 succeeded，避免恢复执行时状态被错误覆盖
            nodes_to_reset = [
                n.get("id", "") for n in sorted_nodes[resume_idx:]
                if n.get("id", "") not in node_results
            ]
            if nodes_to_reset:
                async with _async_session() as reset_db:
                    placeholders = ",".join(f":id_{i}" for i in range(len(nodes_to_reset)))
                    params = {f"id_{i}": nid for i, nid in enumerate(nodes_to_reset)}
                    params["run_id"] = run_id
                    await reset_db.execute(
                        text(
                            f"UPDATE workflow_run_history SET status='pending', updated_at=:now "
                            f"WHERE run_id=:run_id AND node_id IN ({placeholders})"
                        ),
                        {**params, "now": datetime.now(timezone.utc)},
                    )
                    await reset_db.commit()
            logger.info(
                "[workflow] resume: restored %d succeeded nodes, will re-run from %s",
                len(node_results), resume_from,
            )
        else:
            logger.warning("[workflow] resume_from node %s not found in sorted nodes", resume_from)

    for node in sorted_nodes:
        node_id = node.get("id", "")
        result: dict[str, Any] | None = None

        # ── 恢复模式：跳过已成功的节点 ──
        if resume_from and node_id in node_results and not node_results[node_id].get("_failed"):
            logger.info("[workflow] resume: skipping succeeded node=%s", node_id)
            continue

        # 检查上游节点是否全部成功，若有失败则跳过当前节点
        upstream_ids = node.get("inputs", []) or []
        failed_upstream = [
            uid for uid in upstream_ids
            if uid in node_results and node_results[uid].get("_failed")
        ]
        if failed_upstream:
            result = {"outputs": [{"type": "text", "value": f"上游节点失败，已跳过: {', '.join(failed_upstream)}"}]}
            status = "skipped"
            logger.warning("[workflow] node=%s skipped due to failed upstream: %s", node_id, failed_upstream)
            # 直接写入 DB 并 continue
            async with _async_session() as bg_db:
                now_ts = datetime.now(timezone.utc)
                await bg_db.execute(
                    text(
                        "UPDATE workflow_run_history "
                        "SET status = :status, result = :result, updated_at = :updated_at "
                        "WHERE run_id = :run_id AND node_id = :node_id"
                    ),
                    {
                        "status": status,
                        "result": json.dumps(result, ensure_ascii=False),
                        "updated_at": now_ts,
                        "run_id": run_id,
                        "node_id": node_id,
                    },
                )
                await bg_db.commit()
            node_results[node_id] = {**result, "_failed": True}
            continue

        async with _async_session() as bg_db:
            status = "succeeded"  # 默认成功，后续按实际结果覆盖
            try:
                # 将当前节点状态从 pending 改为 running（视觉上标识正在执行）
                now_ts = datetime.now(timezone.utc)
                await bg_db.execute(
                    text(
                        "UPDATE workflow_run_history "
                        "SET status = :status, updated_at = :updated_at "
                        "WHERE run_id = :run_id AND node_id = :node_id"
                    ),
                    {"status": "running", "updated_at": now_ts, "run_id": run_id, "node_id": node_id},
                )
                await bg_db.commit()

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

                # 从上游节点 meta 注入 all_urls（供 ImageInput 的 image_index 使用）
                params_field = node.get("params", {}) or {}
                for ref_key, ref_val in params_field.items():
                    if isinstance(ref_val, str):
                        m = _TEMPLATE_REF_RE.match(ref_val)
                        if m:
                            upstream_id = m.group(1)
                            upstream_result = node_results.get(upstream_id, {})
                            upstream_meta = upstream_result.get("meta", {}) or {}
                            all_urls = upstream_meta.get("all_urls")
                            if all_urls:
                                input_params["all_urls"] = all_urls
                                # 同时按 image_index 设置正确的 image_url（边解析只传了 outputs[0]）
                                img_idx_raw = input_params.get("image_index") if input_params.get("image_index") is not None else input_params_raw.get("image_index")
                                if img_idx_raw is not None:
                                    try:
                                        img_idx = int(img_idx_raw)
                                    except (ValueError, TypeError):
                                        img_idx = 0
                                    urls = all_urls.split(",")
                                    if 0 <= img_idx < len(urls):
                                        input_params["image_url"] = urls[img_idx]
                                        # 同步写回 node.input_params，确保前端表单显示正确的 URL
                                        node_input_params = node.get("input_params", None)
                                        if isinstance(node_input_params, dict):
                                            node_input_params["image_url"] = urls[img_idx]
                                            node["input_params"] = node_input_params
                                logger.info(
                                    "[workflow] injected all_urls+image_url from %s into %s (len=%d, index=%s)",
                                    upstream_id, node_id, len(all_urls), img_idx_raw,
                                )

                # ── 收集所有上游节点的全部图片输出到 images_list ──
                # 对于 image-grid-merge 等需要接收多个上游图片批次的节点，
                # 遍历所有连接到 imageInput2（images_list handle）的边，
                # 收集每个上游节点的全部输出（而非仅 outputs[0]）。
                node_id_str = node.get("id", "")
                # 检查节点 schema 是否包含 images_list 字段
                node_form_values = node.get("formValues", {}) or {}
                has_images_list_field = "images_list" in (node.get("input_params", {}) or {}) or \
                                        "images_list" in node_form_values or \
                                        any(
                                            (node.get("model", "") == comp_id or node.get("category", "") == comp_id)
                                            for comp_id in ("image-grid-merge",)
                                        )
                if has_images_list_field or "images_list" in input_params:
                    all_upstream_images: list[str] = []
                    for edge in (edges or []):
                        if edge.get("target") != node_id_str:
                            continue
                        target_handle = edge.get("targetHandle", "")
                        # imageInput2 = images_list handle (green, multi-input)
                        if target_handle != "imageInput2":
                            continue
                        source_id = edge.get("source", "")
                        source_outputs = node_outputs.get(source_id, [])
                        for out in source_outputs:
                            val = out.get("value")
                            if val and isinstance(val, str) and val.strip():
                                if val not in all_upstream_images:
                                    all_upstream_images.append(val)

                    if all_upstream_images:
                        input_params["images_list"] = all_upstream_images
                        logger.info(
                            "[workflow] collected %d upstream images into images_list for node=%s",
                            len(all_upstream_images), node_id_str,
                        )

                # ── 基于 handle 的边注入 ──
                # 当 params 中没有模板引用时，通过边的 targetHandle → input_param_key
                # 映射直接从上游节点输出注入值。
                # 这解决了前端未设置模板引用时，边连接的数据无法传递的问题。
                HANDLE_TO_PARAM: dict[str, str] = {
                    "imageInput3": "image_url",    # 图片输入 → image_url
                    "imageInput4": "video_url",    # 视频输入 → video_url
                    "videoInput":  "prompt",       # 文本输入到视频节点 → prompt
                    "videoInput2": "image_url",    # 图片输入到视频节点 → image_url
                    "audioInput":  "prompt",       # 文本输入到音频节点 → prompt
                    "audioInput2": "audio_url",    # 音频输入 → audio_url
                    "textInput":   "prompt",       # 文本输入 → prompt
                }
                for edge in (edges or []):
                    if edge.get("target") != node_id_str:
                        continue
                    target_handle = edge.get("targetHandle", "")
                    param_key = HANDLE_TO_PARAM.get(target_handle)
                    if not param_key:
                        continue
                    # 如果 input_params 已有非空值，跳过（用户手动填写优先）
                    current_val = input_params.get(param_key)
                    if current_val and isinstance(current_val, str) and current_val.strip():
                        continue
                    # 从上游节点输出注入
                    source_id = edge.get("source", "")
                    source_outputs = node_outputs.get(source_id, [])
                    if source_outputs:
                        val = source_outputs[0].get("value")
                        if val and isinstance(val, str) and val.strip():
                            input_params[param_key] = val
                            logger.info(
                                "[workflow] edge-injected %s from %s[%s]→%s[%s] for node=%s",
                                param_key, source_id, edge.get("sourceHandle", ""),
                                node_id_str, target_handle, node_id_str,
                            )

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
                                resolved_params = await _refresh_cos_urls(input_params)
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

                # 存储节点输出，供下游节点解析边缘引用
                if result and isinstance(result, dict):
                    outputs_list = result.get("outputs", [])
                    if outputs_list:
                        node_outputs[node_id] = outputs_list
                    node_results[node_id] = {**result, "_failed": status == "failed"}

                # 将成功节点的图片输出保存到本地持久化目录
                if status == "succeeded" and result and isinstance(result, dict):
                    try:
                        result = await _save_outputs_to_local(
                            result=result,
                            run_id=run_id,
                            node_id=node_id,
                        )
                        # 更新内存中的引用，供后续节点和 DB 写入使用
                        outputs_list = result.get("outputs", [])
                        if outputs_list:
                            node_outputs[node_id] = outputs_list
                        node_results[node_id] = result
                    except Exception as e:
                        logger.error(
                            "[workflow] local save error for node %s: %s", node_id, e
                        )

                # 更新运行记录（含修正后的 node_data，前端表单能看到正确的 image_url）
                # 使用原生 SQL 避免 AsyncSession + update(ORMEntity) 的 rowcount 检查问题
                now_ts = datetime.now(timezone.utc)
                await bg_db.execute(
                    text(
                        "UPDATE workflow_run_history "
                        "SET status = :status, result = :result, node_data = :node_data, updated_at = :updated_at "
                        "WHERE run_id = :run_id AND node_id = :node_id"
                    ),
                    {
                        "status": status,
                        "result": json.dumps(result, ensure_ascii=False) if result is not None else None,
                        "node_data": json.dumps(node, ensure_ascii=False) if node is not None else None,
                        "updated_at": now_ts,
                        "run_id": run_id,
                        "node_id": node_id,
                    },
                )
                await bg_db.commit()

            except Exception as e:
                logger.error(f"Error running node {node_id}: {e}")
                result = {"outputs": [{"type": "text", "value": f"Error: {str(e)}"}]}
                status = "failed"
                # 内存中存储错误结果，供下游节点感知该节点失败
                node_results[node_id] = {**result, "_failed": True}

    logger.info("[workflow] run_id=%s all nodes executed", run_id)


async def resume_workflow_helper(db: AsyncSession, workflow_id: str) -> dict:
    """
    准备从失败节点恢复执行。

    1. 查找当前活跃 run_id
    2. 查找第一个 failed/pending 节点作为 resume 起点
    3. 返回 run_id, resume_from, nodes_data, edges 供后台执行
    """
    wf = await _get_workflow(db, workflow_id)

    # 查找当前活跃 run
    result = await db.execute(
        select(RunHistory.run_id)
        .where(RunHistory.workflow_id == workflow_id)
        .limit(1)
    )
    active_run = result.first()
    if not active_run:
        raise HTTPException(status_code=400, detail="没有活跃的运行记录，请先全部运行")
    run_id = active_run[0]

    # 查询所有节点状态，按拓扑顺序找出第一个需要重新执行的节点
    rows = await db.execute(
        select(RunHistory.node_id, RunHistory.status)
        .where(RunHistory.run_id == run_id)
    )
    node_statuses: dict[str, str] = {}
    for row in rows.fetchall():
        nid, nstatus = row
        node_statuses[nid] = nstatus or "pending"

    nodes_data = wf.data.get("nodes", []) if isinstance(wf.data, dict) else []
    edges = wf.edges or []
    sorted_nodes = _topological_sort(nodes_data, edges)

    # 找第一个非 succeeded 的节点
    resume_from: str | None = None
    for node in sorted_nodes:
        nid = node.get("id", "")
        status = node_statuses.get(nid, "pending")
        if status != "succeeded":
            resume_from = nid
            break

    if not resume_from:
        # 所有节点都已成功，无需恢复
        raise HTTPException(status_code=400, detail="所有节点均已成功，无需恢复")

    logger.info(
        "[workflow] resume: run_id=%s, resume_from=%s, failed/pending nodes: %s",
        run_id, resume_from,
        [nid for nid, s in node_statuses.items() if s != "succeeded"],
    )

    return {
        "run_id": run_id,
        "resume_from": resume_from,
        "nodes_data": nodes_data,
        "workflow_id": workflow_id,
        "edges": edges,
    }


async def run_node_helper(db: AsyncSession, workflow_id: str, node_id: str, payload: dict) -> dict:
    """
    POST /api/workflow/{id}/node/{nid}/run
    运行单个节点

    设计：单节点运行始终复用当前活跃 run_id，在该 run 内 upsert 该节点的记录。
    如果该工作流还没有活跃 run（全新工作流），则自动创建一个。
    不管单节点运行多少次，始终在同一 run 内更新，不产生新的 run_id。
    只有点击「全部运行」才会归档旧记录并创建全新 run。
    """
    _ = await _get_workflow(db, workflow_id)

    # ── 查找当前活跃 run_id，没有则创建 ──
    result = await db.execute(
        select(RunHistory.run_id)
        .where(RunHistory.workflow_id == workflow_id)
        .limit(1)
    )
    active_run = result.first()
    run_id = active_run[0] if active_run else gen_uuid()

    # ── 删除该节点在此 run 中的旧记录（upsert 语义） ──
    await db.execute(
        text("DELETE FROM workflow_run_history WHERE run_id = :run_id AND node_id = :node_id"),
        {"run_id": run_id, "node_id": node_id},
    )

    node_run_id = gen_uuid()

    model_id = payload.get("model", "")
    input_params = dict(payload.get("input_params", payload.get("params", {})) or {})
    category = payload.get("category", "")

    # ── 边注入：从上游节点输出补充缺失的参数 ──
    # 单节点运行时，前端传来的 input_params 可能缺少上游连线的数据
    # （如 video_url 为 null）。通过 edges + DB 查找上游节点输出并注入。
    HANDLE_TO_PARAM: dict[str, str] = {
        "imageInput3": "image_url",
        "imageInput4": "video_url",
        "videoInput":  "prompt",
        "videoInput2": "image_url",
        "videoInput4": "video_url",
        "audioInput":  "prompt",
        "audioInput2": "audio_url",
        "textInput":   "prompt",
    }
    try:
        wf = await _get_workflow(db, workflow_id)
        wf_edges = wf.edges or []
        # 查找当前 run 中所有节点的最新输出
        edge_rows = await db.execute(
            text(
                "SELECT node_id, result FROM workflow_run_history "
                "WHERE run_id = :run_id AND status = 'succeeded'"
            ),
            {"run_id": run_id},
        )
        upstream_outputs: dict[str, list[dict]] = {}
        for erow in edge_rows.fetchall():
            src_nid, src_result = erow
            if src_result:
                rj = json.loads(src_result) if isinstance(src_result, str) else src_result
                outs = rj.get("outputs", []) if isinstance(rj, dict) else []
                if outs:
                    upstream_outputs[src_nid] = outs

        injected_keys: list[str] = []
        for edge in wf_edges:
            if edge.get("target") != node_id:
                continue
            target_handle = edge.get("targetHandle", "")
            param_key = HANDLE_TO_PARAM.get(target_handle)
            if not param_key:
                continue
            # 如果已有非空值，跳过
            current_val = input_params.get(param_key)
            if current_val and isinstance(current_val, str) and current_val.strip():
                continue
            source_id = edge.get("source", "")
            src_outs = upstream_outputs.get(source_id, [])
            if src_outs:
                val = src_outs[0].get("value")
                if val and isinstance(val, str) and val.strip():
                    input_params[param_key] = val
                    injected_keys.append(param_key)
                    logger.info(
                        "[run_node] edge-injected %s from %s→%s for node=%s",
                        param_key, source_id, node_id, node_id,
                    )
        if injected_keys:
            logger.info("[run_node] node=%s injected params from edges: %s", node_id, injected_keys)

        # ── 收集 images_list：从所有连接到 imageInput2 的上游节点收集全部输出 ──
        if "images_list" in input_params or model_id in ("image-grid-merge",):
            all_upstream_images: list[str] = []
            for edge in wf_edges:
                if edge.get("target") != node_id:
                    continue
                target_handle = edge.get("targetHandle", "")
                if target_handle != "imageInput2":
                    continue
                source_id = edge.get("source", "")
                src_outs = upstream_outputs.get(source_id, [])
                for out in src_outs:
                    val = out.get("value")
                    if val and isinstance(val, str) and val.strip():
                        if val not in all_upstream_images:
                            all_upstream_images.append(val)
            if all_upstream_images:
                input_params["images_list"] = all_upstream_images
                logger.info(
                    "[run_node] collected %d upstream images into images_list for node=%s",
                    len(all_upstream_images), node_id,
                )
    except Exception as edge_err:
        logger.warning("[run_node] edge injection failed for node=%s: %s", node_id, edge_err)

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

    # ── 先提交初始记录（释放写锁，避免 AI 生成期间阻塞其他请求）──
    # 捕获 node_run_id 和记录主键，commit 后 ORM 对象会 expire，不再直接操作
    _row_id = node_run.id
    await db.commit()
    # 显式 expunge，避免后续设置属性时 SQLAlchemy 尝试 ORM flush 导致 "0 rows matched"
    db.expunge(node_run)

    # 用局部变量跟踪执行结果，不再操作 ORM 对象
    _final_status = "succeeded"
    _final_result: dict[str, Any] | None = None

    try:
        service = get_service(model_id)
        if service:
            result = await service.generate(input_params, model=model_id)
            _final_status = "succeeded"
            _final_result = result
        else:
            # 尝试从 ComponentRegistry 查找自定义组件
            component = ComponentRegistry.get(model_id)
            if component:
                try:
                    component_credentials = ComponentRegistry.get_credentials(model_id)
                    resolved_params = await _refresh_cos_urls(input_params)
                    result = await component.execute(
                        inputs=resolved_params,
                        params=resolved_params,
                        credentials=component_credentials,
                    )
                    _final_status = "succeeded"
                    _final_result = result
                    logger.info(f"Custom component {model_id} executed successfully")
                except Exception as comp_err:
                    _final_status = "failed"
                    _final_result = {
                        "outputs": [
                            {"type": "text", "value": f"组件执行失败: {str(comp_err)}"}
                        ]
                    }
                    logger.error(f"Custom component {model_id} failed: {comp_err}")
            else:
                _final_status = "failed"
                _final_result = {
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
        _final_status = "failed"
        _final_result = {
            "outputs": [{"type": "text", "value": f"运行失败: {str(e)}"}]
        }

    # ── 将成功节点的图片输出保存到本地持久化目录 ──
    # 单节点运行也需要持久化，否则前端无法通过 /api/workflow/runs/... 加载图片
    if _final_status == "succeeded" and _final_result and isinstance(_final_result, dict):
        try:
            _final_result = await _save_outputs_to_local(
                result=_final_result,
                run_id=run_id,
                node_id=node_id,
            )
        except Exception as save_err:
            logger.error(
                "[run_node_helper] local save error for node %s: %s", node_id, save_err
            )

    # 使用原生 SQL UPDATE 写入结果（不依赖 ORM 对象）
    _now_ts = datetime.now(timezone.utc)
    try:
        await db.execute(
            text(
                "UPDATE workflow_run_history "
                "SET status = :status, result = :result, updated_at = :updated_at "
                "WHERE id = :id"
            ),
            {
                "status": _final_status,
                "result": json.dumps(_final_result, ensure_ascii=False) if _final_result is not None else None,
                "updated_at": _now_ts,
                "id": _row_id,
            },
        )
        await db.commit()
    except Exception as update_err:
        logger.error(
            "[run_node_helper] UPDATE failed for node=%s id=%s: %s\n%s",
            node_id, _row_id, update_err, traceback.format_exc(),
        )
        raise
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
        text("DELETE FROM workflow_run_history WHERE node_run_id = :nrid"),
        {"nrid": node_run_id},
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


async def proxy_download_stream(url: str, filename: str = "download"):
    """后端代理下载：服务端拉取文件并返回异步生成器，绕过浏览器 CORS 限制"""
    import httpx
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                yield chunk


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
