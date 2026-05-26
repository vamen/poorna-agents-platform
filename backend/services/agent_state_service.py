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
    import json as _json

    async with AsyncSessionLocal() as session:
        row = await session.execute(sa.text("""
            SELECT value FROM agent_state
            WHERE agent_id = :agent_id
              AND workflow_id = :workflow_id
              AND key = :key
        """), {"agent_id": agent_id, "workflow_id": workflow_id, "key": key})
        result = row.fetchone()
        if result is None:
            return default
        val = result[0]
        # Raw SQL returns a string; JSON columns return parsed — handle both
        if isinstance(val, str):
            return _json.loads(val)
        return val


async def set_state(
    agent_id: str,
    workflow_id: str,
    key: str,
    value: Any,
) -> None:
    """Upsert *value* for *key* scoped to (agent_id, workflow_id).

    Uses a raw SQL upsert so updated_at is always refreshed, even when the
    value hasn't changed (SQLAlchemy ORM skips UPDATEs for identical JSON).
    """
    import json
    from uuid import uuid4

    value_json = json.dumps(value)
    new_id = str(uuid4())

    async with AsyncSessionLocal() as session:
        # SQLite UPSERT — always touches updated_at
        await session.execute(sa.text("""
            INSERT INTO agent_state (id, agent_id, workflow_id, key, value, updated_at)
            VALUES (:id, :agent_id, :workflow_id, :key, :value, CURRENT_TIMESTAMP)
            ON CONFLICT (agent_id, workflow_id, key)
            DO UPDATE SET
                value      = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """), {
            "id": new_id,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "key": key,
            "value": value_json,
        })
        await session.commit()
        logger.debug(
            "agent_state upsert: agent=%s workflow=%s key=%s count=%s",
            agent_id[:8], workflow_id[:8], key,
            len(value) if isinstance(value, (list, dict)) else "-",
        )
