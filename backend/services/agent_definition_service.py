"""CRUD and registry management for user-defined AgentDefinitions."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AgentDefinition
from schemas.agent_definition import AgentDefinitionCreate, AgentDefinitionUpdate


async def list_definitions(db: AsyncSession, org_id: str) -> list[AgentDefinition]:
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.org_id == org_id)
    )
    return list(result.scalars().all())


async def get_definition(db: AsyncSession, def_id: str) -> Optional[AgentDefinition]:
    result = await db.execute(
        select(AgentDefinition).where(AgentDefinition.id == def_id)
    )
    return result.scalar_one_or_none()


async def get_definition_by_name(
    db: AsyncSession, org_id: str, name: str
) -> Optional[AgentDefinition]:
    result = await db.execute(
        select(AgentDefinition).where(
            AgentDefinition.org_id == org_id,
            AgentDefinition.name == name,
        )
    )
    return result.scalar_one_or_none()


async def create_definition(
    db: AsyncSession,
    data: AgentDefinitionCreate,
    org_id: str,
    user_id: str,
) -> AgentDefinition:
    existing = await get_definition_by_name(db, org_id, data.name)
    if existing:
        raise ValueError(
            f"An agent definition named '{data.name}' already exists in this org"
        )

    defn = AgentDefinition(
        org_id=org_id,
        name=data.name,
        definition=data.to_definition_dict(),
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(defn)
    await db.commit()
    await db.refresh(defn)
    _register_in_runtime(defn)
    return defn


async def update_definition(
    db: AsyncSession,
    defn: AgentDefinition,
    data: AgentDefinitionUpdate,
    user_id: str,
) -> AgentDefinition:
    # Merge patch into existing definition blob
    current: dict = dict(defn.definition)

    if data.display_name is not None:
        current["display_name"] = data.display_name
    if data.description is not None:
        current["description"] = data.description
    if data.is_long_running is not None:
        current["is_long_running"] = data.is_long_running
    if data.reasoning is not None:
        current["reasoning"] = data.reasoning.model_dump(exclude_none=False)
    if data.events is not None:
        current["events"] = [e.model_dump() for e in data.events]

    defn.definition = current
    defn.updated_by = user_id
    await db.commit()
    await db.refresh(defn)
    _register_in_runtime(defn)
    return defn


async def delete_definition(db: AsyncSession, defn: AgentDefinition) -> None:
    from db.models import Agent
    result = await db.execute(
        select(Agent).where(
            Agent.type == defn.name,
            Agent.org_id == defn.org_id,
            Agent.is_active == True,
        ).limit(1)
    )
    if result.scalar_one_or_none():
        raise ValueError(
            f"Cannot delete: active agents of type '{defn.name}' still exist"
        )
    await db.delete(defn)
    await db.commit()
    _deregister_from_runtime(defn.name)


# ── Runtime registry helpers ──────────────────────────────────────────────────

def _register_in_runtime(defn: AgentDefinition) -> None:
    from agents import AGENT_REGISTRY
    from agents.generic import make_generic_class
    from services.template_service import register_custom_template

    cls = make_generic_class(defn)
    AGENT_REGISTRY[defn.name] = cls
    register_custom_template(defn)


def _deregister_from_runtime(name: str) -> None:
    from agents import AGENT_REGISTRY
    from services.template_service import deregister_custom_template

    AGENT_REGISTRY.pop(name, None)
    deregister_custom_template(name)


async def load_all_into_registry(db: AsyncSession) -> None:
    """Called once at application startup to hydrate the registry from DB."""
    result = await db.execute(select(AgentDefinition))
    for defn in result.scalars().all():
        _register_in_runtime(defn)
