"""StandardMessage — the envelope for all agent-to-agent communication.

Every message flowing between nodes in a workflow graph is wrapped in a
StandardMessage before being handed to NodeWrapper.  Using Sender/Recipient
dataclasses (instead of raw agent IDs) lets the system accommodate non-agent
participants — Telegram users, webhook callers, etc. — without changing the
message schema.

Fields
------
message_id    Unique ID for this message instance (auto-generated UUID).
session_id    WorkflowSession ID — groups all messages within one trigger run.
workflow_id   Platform workflow DB ID.
sender        Who sent the message (agent or external participant).
recipient     Who should receive the message.
event_name    Namespaced event string, e.g. "telegram.message.received".
payload       The raw event data passed to the receiving agent's run().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class Sender:
    """Identity of a message sender."""
    type: str       # "agent" | "telegram_user" | "system" | …
    ref_id: str     # agent DB id, telegram chat_id, etc.
    display_name: str = ""


@dataclass
class Recipient:
    """Identity of a message recipient."""
    type: str
    ref_id: str
    display_name: str = ""


@dataclass
class StandardMessage:
    session_id: str
    workflow_id: str
    sender: Sender
    recipient: Recipient
    event_name: str
    payload: dict
    message_id: str = field(default_factory=lambda: str(uuid4()))
