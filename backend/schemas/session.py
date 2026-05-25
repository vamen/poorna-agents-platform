from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class SessionCreate(BaseModel):
    workflow_id: str
    trigger_event: str
    trigger_payload: Optional[dict[str, Any]] = None


class MessageResponse(BaseModel):
    id: str
    session_id: str
    from_agent_id: str
    to_agent_id: str
    event_name: str
    payload: Optional[dict[str, Any]] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    id: str
    workflow_id: str
    trigger_event: str
    trigger_payload: Optional[dict[str, Any]] = None
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SessionDetailResponse(SessionResponse):
    messages: list[MessageResponse] = []
