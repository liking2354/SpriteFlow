"""执行器 — 按拓扑序调度节点，缓存命中检查，并发执行"""

from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from datetime import datetime

from .dag import DAG, NodeDef
from .node import create_node, get_node_registry
from .cache import CacheManager, compute_cache_key
from .context import Context
from .types import PortType

_log = logging.getLogger("spriteflow.executor")


class RunStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class NodeRunResult:
    """单个节点的执行结果"""

    node_id: str
    status: RunStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    cache_hit: bool = False
    error: str | None = None
    asset_id: str | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    started_at: str = ""
    finished_at: str = ""
    node_type: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)  # 执行输入快照（prompt/params 等）


@dataclass
class WorkflowRun:
    """工作流执行实例"""

    run_id: str
    workflow_name: str
    status: RunStatus = RunStatus.PENDING
    results: dict[str, NodeRunResult] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""


class Executor:
    """工作流执行器

    职责：
    1. 按 DAG 拓扑序调度节点
    2. 无依赖的节点可并发执行
    3. 缓存命中时跳过执行
    4. 超时保护 + 重试
    """

    def __init__(
        self,
        cache: CacheManager | None = None,
        router: Any = None,
        storage: Any = None,
        db: Any = None,
        template_db: Any = None,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.cache = cache or CacheManager()
        self.router = router
        self.storage = storage
        self.db = db
        self.template_db = template_db
        self.timeout = timeout
        self.max_retries = max_retries

    async def execute(
        self,
        dag: DAG,
        run: WorkflowRun | None = None,
        run_id: str = "",
        workflow_name: str = "",
    ) -> WorkflowRun:
        """执行整个 DAG 工作流

        如果传入 run，则直接使用该对象更新进度（用于 SSE 实时推送场景）；
        否则创建一个新的 WorkflowRun。
        """
        if run is not None:
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now().isoformat()
        else:
            run = WorkflowRun(
                run_id=run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                workflow_name=workflow_name,
                status=RunStatus.RUNNING,
                started_at=datetime.now().isoformat(),
            )

        ctx = Context(
            cache=self.cache,
            router=self.router,
            storage=self.storage,
            db=self.db,
            template_db=self.template_db,
            run_id=run.run_id,
        )

        # 获取拓扑排序
        order = dag.topological_sort()

        # 按层并发执行：同一层（无相互依赖）的节点并发
        executed: set[str] = set()

        while len(executed) < len(order):
            # 找出当前可执行的节点（所有上游已执行）
            ready = [
                nid for nid in order
                if nid not in executed
                and all(
                    edge.src_node in executed
                    for edge in dag.edges
                    if edge.dst_node == nid
                )
            ]

            if not ready:
                raise RuntimeError("死锁：没有可执行的节点，但还有未执行的节点")

            # 标记就绪节点为 QUEUED（SSE 可感知）
            for nid in ready:
                run.results[nid] = NodeRunResult(
                    node_id=nid,
                    status=RunStatus.QUEUED,
                )

            # 并发执行就绪节点
            tasks = [self._execute_node(dag, nid, ctx, run) for nid in ready]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for nid, result in zip(ready, results):
                if isinstance(result, BaseException):
                    run.status = RunStatus.FAILED
                    run.results[nid] = NodeRunResult(
                        node_id=nid,
                        status=RunStatus.FAILED,
                        error=str(result),
                    )
                    run.finished_at = datetime.now().isoformat()
                    return run
                executed.add(nid)

        run.status = RunStatus.COMPLETED
        run.finished_at = datetime.now().isoformat()
        return run

    async def _execute_node(
        self,
        dag: DAG,
        node_id: str,
        ctx: Context,
        run: WorkflowRun,
    ) -> NodeRunResult:
        """执行单个节点（含缓存检查和重试）"""
        node_def = dag.nodes[node_id]
        node_instance = create_node(node_def.type)
        node_instance.node_id = node_id
        node_type = node_def.type

        # 解析上游输入
        inputs: dict[str, Any] = {}
        input_hashes: dict[str, str] = {}

        upstream = dag.get_upstream(node_id)
        for port_name, (src_id, src_port) in upstream.items():
            src_outputs = ctx.get_node_output(src_id)
            inputs[port_name] = src_outputs[src_port]
            input_hashes[port_name] = ctx.cache.compute_input_hash(src_outputs[src_port])

        # 校验并补全参数
        params = node_instance.validate_params(node_def.params)

        # 缓存检查
        cache_key = compute_cache_key(node_def.type, params, input_hashes)

        if self.cache.exists(cache_key):
            # 缓存命中：尝试加载
            from PIL import Image
            cached_image = self.cache.load_image(cache_key)
            if cached_image is not None:
                outputs = {k: cached_image for k in node_instance.OUTPUTS}
                ctx.set_node_output(node_id, outputs)
                ctx.set_input_hashes(node_id, input_hashes)
                # 缓存命中也尝试持久化（如果之前未保存）
                asset_id, url, thumb_url = await self._persist_outputs(node_id, outputs, ctx)
                result = NodeRunResult(
                    node_id=node_id,
                    status=RunStatus.COMPLETED,
                    outputs=outputs,
                    cache_hit=True,
                    asset_id=asset_id,
                    url=url,
                    thumbnail_url=thumb_url,
                    started_at=datetime.now().isoformat(),
                    finished_at=datetime.now().isoformat(),
                    node_type=node_type,
                )
                run.results[node_id] = result
                ctx.log(f"节点 '{node_id}' 缓存命中，跳过执行")
                return result

        # 标记节点为运行中（SSE 可感知）
        run.results[node_id] = NodeRunResult(
            node_id=node_id,
            status=RunStatus.RUNNING,
            started_at=datetime.now().isoformat(),
            node_type=node_type,
        )

        # 执行节点（含重试）
        # 注意：用 BaseException 而非 Exception 以捕获 SystemExit 等非标准异常
        last_error: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                ctx.set_input_hashes(node_id, input_hashes)
                outputs = await asyncio.wait_for(
                    self._call_execute(node_instance, inputs, params, ctx),
                    timeout=self.timeout,
                )
                break
            except BaseException as e:
                last_error = e
                _log.error(
                    "节点 '%s' 执行异常 type=%s str=%r repr=%r\n%s",
                    node_id, type(e).__qualname__, str(e), repr(e),
                    traceback.format_exc(),
                )
                if attempt < self.max_retries:
                    ctx.log(f"节点 '{node_id}' 第 {attempt + 1} 次执行失败，重试中: {e}")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise RuntimeError(
                        f"节点 '{node_id}' 执行失败（重试 {self.max_retries} 次后）: {e}"
                    ) from e

        # 缓存写入
        from PIL import Image
        for port_name, value in outputs.items():
            if isinstance(value, Image.Image):
                self.cache.save_image(cache_key, value)

        ctx.set_node_output(node_id, outputs)

        # 持久化输出为 Asset
        asset_id, url, thumb_url = await self._persist_outputs(node_id, outputs, ctx)

        node_inputs = ctx.get_node_inputs(node_id)
        result = NodeRunResult(
            node_id=node_id,
            status=RunStatus.COMPLETED,
            outputs=outputs,
            cache_hit=False,
            asset_id=asset_id,
            url=url,
            thumbnail_url=thumb_url,
            started_at=datetime.now().isoformat(),
            finished_at=datetime.now().isoformat(),
            node_type=node_type,
            inputs=node_inputs,
        )
        run.results[node_id] = result
        ctx.log(f"节点 '{node_id}' 执行完成")
        return result

    async def _persist_outputs(
        self,
        node_id: str,
        outputs: dict[str, Any],
        ctx: Context,
    ) -> tuple[str | None, str | None, str | None]:
        """将节点输出的 PIL.Image 自动保存为 Asset，返回 (asset_id, url, thumbnail_url)"""
        from PIL import Image
        import hashlib
        import io

        if ctx.storage is None:
            return None, None, None

        for port_name, value in outputs.items():
            if isinstance(value, Image.Image):
                candidates = [value]
            elif isinstance(value, list):
                candidates = [v for v in value if isinstance(v, Image.Image)]
            else:
                continue

            for img in candidates:
                try:
                    # 编码图片
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    data = buf.getvalue()

                    # 计算内容哈希
                    content_hash = hashlib.sha256(data).hexdigest()[:32]

                    # 上传到存储
                    from ..storage.base import StoragePrefix
                    file_key = f"{content_hash}.png"
                    uri = await ctx.storage.upload(file_key, data, prefix=StoragePrefix.GENERATED)

                    # 生成缩略图
                    thumb = img.copy()
                    thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)
                    thumb_buf = io.BytesIO()
                    thumb.save(thumb_buf, format="PNG")
                    thumb_data = thumb_buf.getvalue()

                    thumb_key = f"{content_hash}.png"
                    thumbnail_uri = await ctx.storage.upload(
                        thumb_key, thumb_data, prefix=StoragePrefix.THUMBNAILS,
                    )

                    # 写入数据库
                    asset_id = content_hash
                    if hasattr(ctx, 'db') and ctx.db is not None:
                        from ..asset_hub.models import Asset
                        asset = Asset(
                            type="image",
                            source="generated",
                            uri=uri,
                            hash=content_hash,
                            width=img.width,
                            height=img.height,
                            thumbnail=thumbnail_uri,
                            tags=[],
                            provenance={"run_id": ctx.run_id, "node_id": node_id, "port": port_name},
                        )
                        await ctx.db.create_asset(asset)
                        asset_id = asset.id

                    ctx.log(f"节点 '{node_id}' 输出已保存为资产: {asset_id}")
                    return asset_id, uri, thumbnail_uri

                except Exception as e:
                    ctx.log(f"节点 '{node_id}' 输出持久化失败: {e}")
                    continue

        return None, None, None

    async def _call_execute(
        self, node_instance: Any, inputs: dict, params: dict, ctx: Context
    ) -> dict:
        """调用节点 execute，兼容同步/异步"""
        result = node_instance.execute(inputs, params, ctx)
        if asyncio.iscoroutine(result):
            result = await result
        return result
