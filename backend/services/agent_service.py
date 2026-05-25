from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent, AgentMessage, Workflow
from schemas.agent import AgentCreate, AgentUpdate
from services.template_service import validate_config


async def list_agents(
    db: AsyncSession,
    org_id: str,
    workflow_id: Optional[str] = None,
) -> list[Agent]:
    """List agents for an org.

    When *workflow_id* is provided, return agents that belong to that workflow
    OR are unscoped (workflow_id IS NULL — legacy / created on /new canvas).
    When it is None, return all org agents (used by the AgentList management page).
    """
    from sqlalchemy import or_

    conditions = [Agent.org_id == org_id, Agent.is_active == True]
    if workflow_id is not None:
        conditions.append(
            or_(Agent.workflow_id == workflow_id, Agent.workflow_id == None)
        )
    result = await db.execute(select(Agent).where(*conditions))
    return result.scalars().all()


async def get_agent(db: AsyncSession, agent_id: str) -> Optional[Agent]:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def create_agent(db: AsyncSession, data: AgentCreate, org_id: str, user_id: str) -> Agent:
    errors = validate_config(data.type, data.config)
    if errors:
        raise ValueError(f"Config validation failed: {'; '.join(errors)}")

    agent = Agent(
        **({"id": data.id} if data.id else {}),
        org_id=org_id,
        workflow_id=data.workflow_id,
        name=data.name,
        type=data.type,
        config=data.config,
        created_by=user_id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def update_agent(db: AsyncSession, agent: Agent, data: AgentUpdate) -> Agent:
    if data.name is not None:
        agent.name = data.name
    if data.config is not None:
        errors = validate_config(agent.type, data.config)
        if errors:
            raise ValueError(f"Config validation failed: {'; '.join(errors)}")
        agent.config = data.config

    await db.commit()
    await db.refresh(agent)
    return agent


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    result = await db.execute(
        select(AgentMessage).where(
            AgentMessage.from_agent_id == agent.id,
        ).limit(1)
    )
    # Check active workflow references via graph_definition
    result2 = await db.execute(select(Workflow).where(Workflow.status == "active"))
    active_workflows = result2.scalars().all()
    for wf in active_workflows:
        nodes = wf.graph_definition.get("nodes", [])
        for node in nodes:
            if node.get("data", {}).get("agent_id") == agent.id:
                raise ValueError("Agent is referenced in an active workflow")

    agent.is_active = False
    await db.commit()
