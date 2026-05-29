from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, model_validator


class SessionCreate(BaseModel):
    workflow_id: str
    trigger_event: str
    trigger_payload: Optional[dict[str, Any]] = None


class MessageResponse(BaseModel):
    id: str
    session_id: str
    # sender / recipient identity
    sender_type: str = "agent"
    sender_ref_id: str = ""
    sender_name: str = ""
    recipient_type: str = "agent"
    recipient_ref_id: str = ""
    recipient_name: str = ""
    event_name: str
    payload: Optional[dict[str, Any]] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _flatten_sender_recipient(cls, data: Any) -> Any:
        """Pull sender/recipient fields from ORM relationships if present."""
        if not isinstance(data, dict):
            # ORM object — pull relationship attrs
            obj = data
            sender = getattr(obj, "sender", None)
            recipient = getattr(obj, "recipient", None)
            return {
                "id": obj.id,
                "session_id": obj.session_id,
                "sender_type": sender.type if sender else "agent",
                "sender_ref_id": sender.ref_id if sender else "",
                "sender_name": sender.display_name if sender else "",
                "recipient_type": recipient.type if recipient else "agent",
                "recipient_ref_id": recipient.ref_id if recipient else "",
                "recipient_name": recipient.display_name if recipient else "",
                "event_name": obj.event_name,
                "payload": obj.payload,
                "status": obj.status,
                "created_at": obj.created_at,
            }
        return data


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
