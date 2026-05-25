"""Standard platform message — the canonical input to every agent's run() method.

Every agent, whether predefined or user-defined, receives exactly this shape.
The fields are available as template variables in prompt templates::

    system: You are processing {{ event_name }} from {{ from_agent }}.
    user:   Payload: {{ payload }}
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class StandardMessage(BaseModel):
    """The canonical input type passed to every agent at execution time.

    Attributes
    ----------
    message_id:
        UUID identifying this specific message delivery.
    session_id:
        UUID of the parent WorkflowSession.
    workflow_id:
        UUID of the parent Workflow.
    event_name:
        The triggering event, e.g. ``"email.received"``.
    payload:
        The data emitted with the event.  Shape depends on the event schema
        defined in the source agent's template.
    from_agent_id:
        UUID of the Agent that emitted the event.
    timestamp:
        UTC datetime when the message was created.
    """

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    workflow_id: str
    event_name: str
    payload: dict[str, Any]
    from_agent_id: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ── template variable helpers ─────────────────────────────────────────

    def template_vars(self) -> dict[str, Any]:
        """Return a flat dict of all fields, ready to use in prompt templates.

        ``payload`` is converted to a pretty-printed JSON string for easy
        embedding in prompts.
        """
        import json

        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "event_name": self.event_name,
            "payload": json.dumps(self.payload, indent=2, default=str),
            "from_agent_id": self.from_agent_id,
            "timestamp": self.timestamp.isoformat(),
        }
