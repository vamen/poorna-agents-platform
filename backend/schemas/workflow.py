from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class WorkflowCreate(BaseModel):
    name: str
    template_slug: Optional[str] = None
    graph_definition: dict[str, Any] = {"nodes": [], "edges": []}


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    graph_definition: Optional[dict[str, Any]] = None


class WorkflowResponse(BaseModel):
    id: str
    org_id: str
    name: str
    template_slug: Optional[str] = None
    graph_definition: dict[str, Any]
    compiled_graph: Optional[dict[str, Any]] = None
    temporal_workflow_id: Optional[str] = None
    status: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WorkflowSummary(BaseModel):
    id: str
    name: str
    template_slug: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowTemplateResponse(BaseModel):
    slug: str
    name: str
    description: str
    graph_definition: dict[str, Any]


class DeployResponse(BaseModel):
    status: str
    temporal_workflow_id: Optional[str] = None


class StatusResponse(BaseModel):
    status: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str]
