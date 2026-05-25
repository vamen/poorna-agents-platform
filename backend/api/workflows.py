from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.base import get_db
from schemas.workflow import (
    DeployResponse,
    StatusResponse,
    ValidationResult,
    WorkflowCreate,
    WorkflowResponse,
    WorkflowSummary,
    WorkflowTemplateResponse,
    WorkflowUpdate,
)
from services import workflow_service

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.get("/templates", response_model=list[WorkflowTemplateResponse])
async def list_workflow_templates():
    return workflow_service.get_workflow_templates()


@router.get("/templates/{slug}", response_model=WorkflowTemplateResponse)
async def get_workflow_template(slug: str):
    tmpl = workflow_service.get_workflow_template(slug)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Workflow template not found")
    return tmpl


@router.get("", response_model=list[WorkflowSummary])
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await workflow_service.list_workflows(db, current_user["org_id"])


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    data: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await workflow_service.create_workflow(db, data, current_user["org_id"], current_user["id"])


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    data: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        return await workflow_service.update_workflow(db, wf, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        await workflow_service.delete_workflow(db, wf)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{workflow_id}/sessions")
async def list_sessions(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from sqlalchemy import select
    from db.models import WorkflowSession
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    result = await db.execute(
        select(WorkflowSession).where(WorkflowSession.workflow_id == workflow_id)
    )
    return result.scalars().all()


@router.post("/{workflow_id}/validate", response_model=ValidationResult)
async def validate_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    errors = workflow_service.validate_workflow_graph(wf.graph_definition)
    return ValidationResult(valid=len(errors) == 0, errors=errors)


@router.post("/{workflow_id}/deploy", response_model=DeployResponse)
async def deploy_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        return await workflow_service.deploy_workflow(db, wf)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{workflow_id}/pause", response_model=StatusResponse)
async def pause_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await workflow_service.pause_workflow_action(db, wf)


@router.post("/{workflow_id}/resume", response_model=StatusResponse)
async def resume_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    wf = await workflow_service.get_workflow(db, workflow_id)
    if not wf or wf.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await workflow_service.resume_workflow_action(db, wf)
