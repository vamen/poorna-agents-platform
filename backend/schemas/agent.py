from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class AgentCreate(BaseModel):
    id: Optional[str] = None            # client may supply a pre-generated UUID
    workflow_id: Optional[str] = None   # scope agent to a specific workflow canvas
    name: str
    type: str
    config: dict[str, Any] = {}


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None


class AgentResponse(BaseModel):
    id: str
    org_id: str
    workflow_id: Optional[str] = None
    name: str
    type: str
    config: dict[str, Any]
    is_active: bool
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TemplateEvent(BaseModel):
    name: str
    payload: dict[str, Any] = {}   # {event_schema_type, value}


class TemplateResponse(BaseModel):
    """Lightweight summary of an agent type, used by the canvas palette
    and edge event selector. Predefined templates and custom AgentDefinitions
    both produce this shape."""
    name: str          # machine identifier — was 'type', renamed for consistency
    display_name: str
    description: str
    is_long_running: bool = False
    events: list[TemplateEvent] = []
    tools: list[str] = []         # standard platform tools declared in reasoning
    mcp_servers: list[str] = []   # MCP server names declared in reasoning
