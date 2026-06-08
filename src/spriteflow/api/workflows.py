"""工作流 API — 提交、执行状态、进度"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..engine.executor import RunStatus, WorkflowRun
from ..workflow.yaml_loader import WorkflowLoader
from .deps import get_executor

router = APIRouter()

# 内存中的运行记录（生产环境应持久化）
_runs: dict[str, WorkflowRun] = {}


class WorkflowSubmit(BaseModel):
    """工作流提交请求"""

    yaml_path: str | None = None
    workflow: dict | None = None


class WorkflowRunResponse(BaseModel):
    """工作流执行响应"""

    run_id: str = Field(serialization_alias="runId")
    status: str
    results: dict[str, Any] = {}

    model_config = {"populate_by_name": True}


@router.post("/workflows", response_model=WorkflowRunResponse)
async def submit_workflow(body: WorkflowSubmit):
    """提交工作流执行"""
    try:
        if body.yaml_path:
            dag, name = WorkflowLoader.load(body.yaml_path)
        elif body.workflow:
            dag, name = WorkflowLoader.load_from_dict(body.workflow)
        else:
            raise HTTPException(status_code=400, detail="需要 yaml_path 或 workflow 参数")

        # 验证
        errors = WorkflowLoader.validate(dag)
        if errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 执行
    executor = get_executor()
    run = await executor.execute(dag, workflow_name=name)

    _runs[run.run_id] = run

    return WorkflowRunResponse(
        run_id=run.run_id,
        status=run.status.value,
        results={
            nid: {
                "status": r.status.value,
                "cacheHit": r.cache_hit,
                "error": r.error,
            }
            for nid, r in run.results.items()
        },
    )


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_run_status(run_id: str):
    """查询执行状态"""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")

    return WorkflowRunResponse(
        run_id=run.run_id,
        status=run.status.value,
        results={
            nid: {
                "status": r.status.value,
                "cacheHit": r.cache_hit,
                "error": r.error,
            }
            for nid, r in run.results.items()
        },
    )
