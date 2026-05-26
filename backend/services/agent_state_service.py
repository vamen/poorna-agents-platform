"""Agent state persistence service.

Provides get/set for arbitrary key-value state scoped to (agent_id, workflow_id).
Used by long-running agents (e.g. GmailWatcher) to persist cursor state across
worker restarts so no emails are double-processed or missed.

Usage inside a Temporal activity::

    from services.agent_state_service import get_state, set_state

    seen_ids = await get_state(agent_id, workflow_id, "seen_ids", default=[])
    # ... do work ...
    await set_state(agent_id, workflow_id, "seen_ids", list(seen_ids))
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy as sa

from db.base import AsyncSessionLocal
from db.models import AgentState

logger = logging.getLogger(__name__)


async def get_state(
    agent_id: str,
    workflow_id: str,
    key: str,
    default: Any = None,
) -> Any:
    """Return the stored value for *key*, or *default* if not found."""
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            sa.select(AgentState).where(
                AgentState.agent_id == agent_id,
                AgentState.workflow_id == workflow_id,
                AgentState.key == key,
            )
        )
        state = row.scalar_one_or_none()
        if state is None:
            return default
        return state.value


async def set_state(
    agent_id: str,
    workflow_id: str,
    key: str,
    value: Any,
) -> None:
    """Upsert *value* for *key* scoped to (agent_id, workflow_id)."""
    from uuid import uuid4

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            sa.select(AgentState).where(
                AgentState.agent_id == agent_id,
                AgentState.workflow_id == workflow_id,
                AgentState.key == key,
            )
        )
        state = row.scalar_one_or_none()
        if state is None:
            session.add(AgentState(
                id=str(uuid4()),
                agent_id=agent_id,
                workflow_id=workflow_id,
                key=key,
                value=value,
            ))
        else:
            state.value = value
        await session.commit()
        logger.debug(
            "agent_state upsert: agent=%s workflow=%s key=%s",
            agent_id, workflow_id, key,
        )
