from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agents import get_agent_class
from api.deps import get_current_user
from db.base import get_db
from schemas.agent import AgentCreate, AgentResponse, AgentUpdate, TemplateEvent, TemplateResponse
from services import agent_service, template_service

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates():
    return template_service.get_all_templates()


@router.get("/templates/{type}", response_model=TemplateResponse)
async def get_template(type: str):
    tmpl = template_service.get_template(type)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    workflow_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await agent_service.list_agents(db, current_user["org_id"], workflow_id=workflow_id)


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        return await agent_service.create_agent(db, data, current_user["org_id"], current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    agent = await agent_service.get_agent(db, agent_id)
    if not agent or agent.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    data: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    agent = await agent_service.get_agent(db, agent_id)
    if not agent or agent.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        return await agent_service.update_agent(db, agent, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{agent_id}/events", response_model=list[TemplateEvent])
async def get_agent_events(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return the event schemas this agent instance can emit.

    Looks up the agent's type in the registry and delegates to
    ``BaseAgent.emitted_events()``, keeping the response in sync with
    the YAML template automatically.
    """
    agent = await agent_service.get_agent(db, agent_id)
    if not agent or agent.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_cls = get_agent_class(agent.type)
    if agent_cls is None:
        raise HTTPException(
            status_code=422,
            detail=f"Agent type '{agent.type}' is not registered",
        )
    return agent_cls.emitted_events()


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    agent = await agent_service.get_agent(db, agent_id)
    if not agent or agent.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await agent_service.delete_agent(db, agent)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
