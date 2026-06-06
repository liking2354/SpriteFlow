"""执行器 — 按拓扑序调度节点，缓存命中检查，并发执行"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from datetime import datetime

from .dag import DAG, NodeDef
from .node import create_node, get_node_registry
from .cache import CacheManager, compute_cache_key
from .context import Context
from .types import PortType


class RunStatus(str, Enum):
    PENDING = "pending"
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
    started_at: str = ""
    finished_at: str = ""


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
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.cache = cache or CacheManager()
        self.router = router
        self.storage = storage
        self.db = db
        self.timeout = timeout
        self.max_retries = max_retries

    async def execute(self, dag: DAG, run_id: str = "", workflow_name: str = "") -> WorkflowRun:
        """执行整个 DAG 工作流"""
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

            # 并发执行就绪节点
            tasks = [self._execute_node(dag, nid, ctx, run) for nid in ready]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for nid, result in zip(ready, results):
                if isinstance(result, Exception):
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
                result = NodeRunResult(
                    node_id=node_id,
                    status=RunStatus.COMPLETED,
                    outputs=outputs,
                    cache_hit=True,
                    started_at=datetime.now().isoformat(),
                    finished_at=datetime.now().isoformat(),
                )
                run.results[node_id] = result
                ctx.log(f"节点 '{node_id}' 缓存命中，跳过执行")
                return result

        # 执行节点（含重试）
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                ctx.set_input_hashes(node_id, input_hashes)
                outputs = await asyncio.wait_for(
                    self._call_execute(node_instance, inputs, params, ctx),
                    timeout=self.timeout,
                )
                break
            except Exception as e:
                last_error = e
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
        result = NodeRunResult(
            node_id=node_id,
            status=RunStatus.COMPLETED,
            outputs=outputs,
            cache_hit=False,
            started_at=datetime.now().isoformat(),
            finished_at=datetime.now().isoformat(),
        )
        run.results[node_id] = result
        ctx.log(f"节点 '{node_id}' 执行完成")
        return result

    async def _call_execute(
        self, node_instance: Any, inputs: dict, params: dict, ctx: Context
    ) -> dict:
        """调用节点 execute，兼容同步/异步"""
        result = node_instance.execute(inputs, params, ctx)
        if asyncio.iscoroutine(result):
            result = await result
        return result
