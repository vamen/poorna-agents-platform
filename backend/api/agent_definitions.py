"""REST endpoints for custom AgentDefinitions."""

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from db.base import get_db
from schemas.agent_definition import (
    AgentDefinitionCreate,
    AgentDefinitionResponse,
    AgentDefinitionUpdate,
)
from services import agent_definition_service
from tools import STANDARD_TOOLS

router = APIRouter(prefix="/api/agent-definitions", tags=["agent-definitions"])

_SCHEMA_PATH = Path(__file__).parent.parent / "templates" / "_generic_agent.yaml"


# ── Schema & tools reference ──────────────────────────────────────────────────

@router.get("/schema")
async def get_generic_schema():
    """Return the generic agent JSON Schema (written in YAML) as a parsed dict."""
    with open(_SCHEMA_PATH) as f:
        return yaml.safe_load(f)


@router.get("/tools")
async def list_standard_tools() -> list[dict]:
    """Return descriptions of all tools available to custom agents."""
    return [t.to_dict() for t in STANDARD_TOOLS.values()]


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AgentDefinitionResponse])
async def list_definitions(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    defs = await agent_definition_service.list_definitions(db, current_user["org_id"])
    return [AgentDefinitionResponse.from_orm(d) for d in defs]


@router.post("", response_model=AgentDefinitionResponse, status_code=201)
async def create_definition(
    data: AgentDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        defn = await agent_definition_service.create_definition(
            db, data, current_user["org_id"], current_user["id"]
        )
        return AgentDefinitionResponse.from_orm(defn)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/{def_id}", response_model=AgentDefinitionResponse)
async def get_definition(
    def_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    defn = await agent_definition_service.get_definition(db, def_id)
    if not defn or defn.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Agent definition not found")
    return AgentDefinitionResponse.from_orm(defn)


@router.patch("/{def_id}", response_model=AgentDefinitionResponse)
async def update_definition(
    def_id: str,
    data: AgentDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    defn = await agent_definition_service.get_definition(db, def_id)
    if not defn or defn.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Agent definition not found")
    try:
        updated = await agent_definition_service.update_definition(
            db, defn, data, current_user["id"]
        )
        return AgentDefinitionResponse.from_orm(updated)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/{def_id}", status_code=204)
async def delete_definition(
    def_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    defn = await agent_definition_service.get_definition(db, def_id)
    if not defn or defn.org_id != current_user["org_id"]:
        raise HTTPException(status_code=404, detail="Agent definition not found")
    try:
        await agent_definition_service.delete_definition(db, defn)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
