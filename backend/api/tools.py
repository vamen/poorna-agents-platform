"""Tool & MCP server template API.

Endpoints for the frontend to discover available tools and fetch their
JSON Schema + UI hints for rendering credential configuration forms.

Routes:
  GET /api/tools                    — list all tools (meta only)
  GET /api/tools/{name}/schema      — JSON Schema for config validation
  GET /api/tools/{name}/ui          — UI rendering hints
  GET /api/agents/{agent_id}/tool-configs        — list configured tools
  PUT /api/agents/{agent_id}/tool-configs/{name} — upsert a tool config
  DELETE /api/agents/{agent_id}/tool-configs/{name} — remove a tool config
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from db.models import Agent, AgentToolConfig
from services.tool_registry_service import tool_registry
from uuid import uuid4

router = APIRouter(prefix="/api", tags=["tools"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ToolConfigUpsert(BaseModel):
    kind: str           # "tool" | "mcp_server"
    config: dict[str, Any]


class ToolConfigResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    kind: str
    config: dict[str, Any]
    created_at: str
    updated_at: str | None = None

    @classmethod
    def from_orm(cls, obj: AgentToolConfig) -> "ToolConfigResponse":
        return cls(
            id=obj.id,
            agent_id=obj.agent_id,
            name=obj.name,
            kind=obj.kind,
            config=obj.config,
            created_at=obj.created_at.isoformat() if obj.created_at else "",
            updated_at=obj.updated_at.isoformat() if obj.updated_at else None,
        )


# ── Tool template routes ──────────────────────────────────────────────────────

@router.get("/tools")
async def list_tools() -> list[dict]:
    """List all available tool & MCP server templates (meta only)."""
    return tool_registry.list_tools()


@router.get("/tools/{name}/schema")
async def get_tool_schema(name: str) -> dict:
    """Return the JSON Schema for a tool's credential/config form."""
    schema = tool_registry.get_schema(name)
    if schema is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    return schema


@router.get("/tools/{name}/ui")
async def get_tool_ui(name: str) -> dict:
    """Return the UI hints for a tool's credential/config form."""
    entry = tool_registry.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")
    return entry.ui


# ── Per-agent tool config routes ──────────────────────────────────────────────

async def _get_agent_or_404(agent_id: str, org_id: str, db: AsyncSession) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/agents/{agent_id}/tool-configs")
async def list_agent_tool_configs(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[ToolConfigResponse]:
    """List all tool/MCP configs for an agent."""
    await _get_agent_or_404(agent_id, current_user["org_id"], db)
    result = await db.execute(
        select(AgentToolConfig).where(AgentToolConfig.agent_id == agent_id)
    )
    rows = result.scalars().all()
    return [ToolConfigResponse.from_orm(r) for r in rows]


@router.put("/agents/{agent_id}/tool-configs/{name}")
async def upsert_agent_tool_config(
    agent_id: str,
    name: str,
    body: ToolConfigUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ToolConfigResponse:
    """Create or update a tool/MCP server config for an agent."""
    await _get_agent_or_404(agent_id, current_user["org_id"], db)

    # Validate against tool schema (best-effort — jsonschema optional)
    errors = tool_registry.validate_config(name, body.config)
    if errors:
        raise HTTPException(status_code=422, detail={"config_errors": errors})

    # Upsert
    result = await db.execute(
        select(AgentToolConfig).where(
            AgentToolConfig.agent_id == agent_id,
            AgentToolConfig.name == name,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.kind = body.kind
        existing.config = body.config
        await db.commit()
        await db.refresh(existing)
        return ToolConfigResponse.from_orm(existing)
    else:
        new_config = AgentToolConfig(
            id=str(uuid4()),
            agent_id=agent_id,
            name=name,
            kind=body.kind,
            config=body.config,
        )
        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)
        return ToolConfigResponse.from_orm(new_config)


@router.delete("/agents/{agent_id}/tool-configs/{name}")
async def delete_agent_tool_config(
    agent_id: str,
    name: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Remove a tool/MCP server config from an agent."""
    await _get_agent_or_404(agent_id, current_user["org_id"], db)

    result = await db.execute(
        select(AgentToolConfig).where(
            AgentToolConfig.agent_id == agent_id,
            AgentToolConfig.name == name,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No config for tool '{name}' on this agent")

    await db.delete(existing)
    await db.commit()
    return {"ok": True}
