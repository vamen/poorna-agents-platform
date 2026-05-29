"""Session and message persistence for agent-to-agent communication.

Two responsibilities:
  1. WorkflowSession lifecycle — create one session per trigger event run.
  2. AgentMessage CRUD — save / update every StandardMessage that flows
     between nodes.

Both are called from NodeWrapper and from create_session_activity (Temporal).
They can also be called directly from non-Temporal contexts (chat agents, tests).
"""

from __future__ import annotations

import logging
from uuid import uuid4

import sqlalchemy as sa

from db.base import AsyncSessionLocal
from db.models import AgentMessage, Sender as SenderModel, Recipient as RecipientModel, WorkflowSession

logger = logging.getLogger(__name__)


async def get_or_create_session(
    workflow_id: str,
    trigger_event: str,
    correlation_id: str,
) -> str:
    """Return the session_id for this run, creating a new WorkflowSession if needed.

    Uses (workflow_id, correlation_id) as a natural key so replayed Temporal
    activities don't create duplicate sessions.
    """
    async with AsyncSessionLocal() as db:
        if correlation_id:
            row = await db.execute(
                sa.select(WorkflowSession.id).where(
                    WorkflowSession.workflow_id == workflow_id,
                    WorkflowSession.correlation_id == correlation_id,
                )
            )
            existing = row.scalar_one_or_none()
            if existing:
                return existing

        session_id = str(uuid4())
        db.add(WorkflowSession(
            id=session_id,
            workflow_id=workflow_id,
            trigger_event=trigger_event,
            trigger_payload=None,
            correlation_id=correlation_id or session_id,
            status="running",
        ))
        await db.commit()
        logger.info(
            "Created WorkflowSession %s for workflow %s (corr=%s)",
            session_id[:8], workflow_id[:8], correlation_id[:16] if correlation_id else "-",
        )
        return session_id


async def get_or_create_sender(type: str, ref_id: str, display_name: str = "") -> str:
    """Return the DB id for a Sender row, creating one if it doesn't exist yet."""
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            sa.select(SenderModel.id).where(
                SenderModel.type == type,
                SenderModel.ref_id == ref_id,
            )
        )
        existing = row.scalar_one_or_none()
        if existing:
            return existing

        sender_id = str(uuid4())
        db.add(SenderModel(id=sender_id, type=type, ref_id=ref_id, display_name=display_name))
        await db.commit()
        return sender_id


async def get_or_create_recipient(type: str, ref_id: str, display_name: str = "") -> str:
    """Return the DB id for a Recipient row, creating one if it doesn't exist yet."""
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            sa.select(RecipientModel.id).where(
                RecipientModel.type == type,
                RecipientModel.ref_id == ref_id,
            )
        )
        existing = row.scalar_one_or_none()
        if existing:
            return existing

        recipient_id = str(uuid4())
        db.add(RecipientModel(id=recipient_id, type=type, ref_id=ref_id, display_name=display_name))
        await db.commit()
        return recipient_id


async def save_message(message: "StandardMessage") -> None:  # noqa: F821
    """Insert an AgentMessage row for *message* with status='pending'."""
    sender_id = await get_or_create_sender(
        type=message.sender.type,
        ref_id=message.sender.ref_id,
        display_name=message.sender.display_name,
    )
    recipient_id = await get_or_create_recipient(
        type=message.recipient.type,
        ref_id=message.recipient.ref_id,
        display_name=message.recipient.display_name,
    )

    async with AsyncSessionLocal() as db:
        db.add(AgentMessage(
            id=message.message_id,
            session_id=message.session_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            event_name=message.event_name,
            payload=message.payload,
            status="pending",
        ))
        await db.commit()


async def update_message_status(message_id: str, status: str) -> None:
    """Update the status of an existing AgentMessage row."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa.update(AgentMessage)
            .where(AgentMessage.id == message_id)
            .values(status=status)
        )
        await db.commit()


async def close_session(session_id: str, status: str = "completed") -> None:
    """Mark a WorkflowSession as completed or failed."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa.update(WorkflowSession)
            .where(WorkflowSession.id == session_id)
            .values(status=status)
        )
        await db.commit()
