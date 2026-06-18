from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..workflow_helper import (
    create_or_update_workflow,
    get_node_schemas_helper,
    get_api_node_schemas_helper,
    get_workflow_def_helper,
    run_workflow_helper,
    execute_workflow_run,
    get_run_status_helper,
    run_node_helper,
    publish_workflow_helper,
    template_workflow_helper,
    cloudfront_signed_url_helper,
    generate_thumbnail_helper,
    get_workflow_defs_helper,
    delete_workflow_def_by_id,
    update_workflow_name_helper,
    get_workflow_last_run,
    architect_workflow_helper,
    poll_architect_result_helper,
    delete_node_run_by_id_helper,
    update_workflow_category_helper,
    get_workflow_api_inputs_helper,
    execute_workflow_via_api_helper,
    get_workflow_api_outputs_helper,
    seed_workflow_presets,
    get_workflow_presets,
    get_workflow_preset_detail,
    update_workflow_preset,
)

router = APIRouter()


@router.post("/create")
async def create_workflow(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
        return await create_or_update_workflow(db, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/get-workflow-defs")
async def get_workflow_defs(
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    try:
        return await get_workflow_defs_helper(db, limit=limit, offset=offset)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/get-workflow-def/{workflow_id}")
async def get_workflow_def(workflow_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await get_workflow_def_helper(db, workflow_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/default/node-schemas")
async def get_default_node_schemas(db: AsyncSession = Depends(get_db)):
    try:
        return await get_node_schemas_helper("default", db)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}/node-schemas")
async def get_node_schemas(workflow_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await get_node_schemas_helper(workflow_id, db)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}/api-node-schemas")
async def get_api_node_schemas(workflow_id: str):
    try:
        return await get_api_node_schemas_helper(workflow_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/delete-workflow-def/{workflow_id}")
async def delete_workflow_def(workflow_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await delete_workflow_def_by_id(db, workflow_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/update-name/{workflow_id}")
async def update_workflow_name(
    workflow_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
        return await update_workflow_name_helper(db, workflow_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/update-category/{workflow_id}")
async def update_workflow_category(
    workflow_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
        return await update_workflow_category_helper(db, workflow_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workflow_id}/run")
async def run_workflow(
    workflow_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await request.json()
        prep_result = await run_workflow_helper(db, workflow_id, payload)
        run_id = prep_result["run_id"]
        nodes_data = prep_result.get("nodes_data", [])
        # 后台异步执行节点，立即返回 run_id 供前端轮询
        background_tasks.add_task(execute_workflow_run, run_id, workflow_id, nodes_data)
        return {"run_id": run_id}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/run/{run_id}/status")
async def get_run_status(run_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await get_run_status_helper(db, run_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workflow_id}/node/{node_id}/run")
async def run_node(
    workflow_id: str,
    node_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await request.json()
        return await run_node_helper(db, workflow_id, node_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/node-run/{node_run_id}")
async def delete_node_run(
    node_run_id: str, db: AsyncSession = Depends(get_db)
):
    try:
        return await delete_node_run_by_id_helper(db, node_run_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/get-workflow-last-run/{workflow_id}")
async def get_workflow_last_run_endpoint(
    workflow_id: str, db: AsyncSession = Depends(get_db)
):
    try:
        return await get_workflow_last_run(db, workflow_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/architect")
async def architect_workflow_endpoint(request: Request):
    try:
        payload = await request.json()
        return await architect_workflow_helper(payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/poll-architect/{id}/result")
async def poll_architect_result(id: str):
    try:
        return await poll_architect_result_helper(id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workflow/{workflow_id}/publish")
async def publish_workflow(
    workflow_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
        return await publish_workflow_helper(db, workflow_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/workflow/{workflow_id}/template")
async def template_workflow(
    workflow_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
        return await template_workflow_helper(db, workflow_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cloudfront-signed-url")
async def cloudfront_signed_url(request: Request):
    try:
        payload = await request.json()
        return await cloudfront_signed_url_helper(payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workflow_id}/thumbnail")
async def generate_thumbnail(
    workflow_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
        return await generate_thumbnail_helper(db, workflow_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{workflow_id}/api-inputs")
async def get_workflow_api_inputs(
    workflow_id: str, db: AsyncSession = Depends(get_db)
):
    try:
        return await get_workflow_api_inputs_helper(db, workflow_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{workflow_id}/api-execute")
async def execute_workflow_via_api(
    workflow_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        payload = await request.json()
        return await execute_workflow_via_api_helper(db, workflow_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/run/{run_id}/api-outputs")
async def get_workflow_api_outputs(
    run_id: str, db: AsyncSession = Depends(get_db)
):
    try:
        return await get_workflow_api_outputs_helper(db, run_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


# ===========================================================================
# 工作流预设模板
# ===========================================================================

@router.post("/presets/seed")
async def seed_presets(db: AsyncSession = Depends(get_db)):
    """初始化预设模板数据到数据库"""
    try:
        count = await seed_workflow_presets(db)
        return {"ok": True, "seeded": count}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/presets")
async def list_presets(db: AsyncSession = Depends(get_db)):
    """获取所有预设模板列表"""
    try:
        return await get_workflow_presets(db)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/presets/{preset_id}")
async def get_preset_detail(preset_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个预设模板完整数据"""
    try:
        return await get_workflow_preset_detail(db, preset_id)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """更新预设模板"""
    try:
        payload = await request.json()
        return await update_workflow_preset(db, preset_id, payload)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))
