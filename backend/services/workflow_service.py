from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Workflow, WorkflowSession, AgentMessage
from runtime.compiler import compile_graph
from runtime.temporal_client import start_workflow, pause_workflow
from schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowTemplateResponse


WORKFLOW_TEMPLATES: list[dict] = [
    {
        "slug": "hr_screener",
        "name": "HR Resume Screener",
        "description": "Watches Gmail for incoming resumes, scores against criteria, sends reply",
        "graph_definition": {
            "nodes": [
                {"id": "n1", "type": "agentNode", "position": {"x": 100, "y": 200}, "data": {"label": "Gmail Watcher", "agentType": "gmail_watcher"}},
                {"id": "n2", "type": "agentNode", "position": {"x": 400, "y": 200}, "data": {"label": "Resume Scorer", "agentType": "classifier"}},
                {"id": "n3", "type": "agentNode", "position": {"x": 700, "y": 200}, "data": {"label": "Send Reply", "agentType": "api_caller"}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2", "data": {"event": "email.received"}},
                {"id": "e2", "source": "n2", "target": "n3", "data": {"event": "classification.done"}},
            ],
        },
    },
    {
        "slug": "payment_reconciler",
        "name": "Payment Notification Reconciler",
        "description": "Watches Gmail for payment emails, classifies type, fires configured API",
        "graph_definition": {
            "nodes": [
                {"id": "n1", "type": "agentNode", "position": {"x": 100, "y": 200}, "data": {"label": "Gmail Watcher", "agentType": "gmail_watcher"}},
                {"id": "n2", "type": "agentNode", "position": {"x": 400, "y": 200}, "data": {"label": "Payment Classifier", "agentType": "classifier"}},
                {"id": "n3", "type": "agentNode", "position": {"x": 700, "y": 100}, "data": {"label": "Notify System", "agentType": "api_caller"}},
                {"id": "n4", "type": "agentNode", "position": {"x": 700, "y": 300}, "data": {"label": "Alert Operator", "agentType": "telegram_gateway"}},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2", "data": {"event": "email.received"}},
                {"id": "e2", "source": "n2", "target": "n3", "data": {"event": "classification.done"}},
                {"id": "e3", "source": "n2", "target": "n4", "data": {"event": "classification.failed"}},
            ],
        },
    },
]


async def list_workflows(db: AsyncSession, org_id: str) -> list[Workflow]:
    result = await db.execute(select(Workflow).where(Workflow.org_id == org_id))
    return result.scalars().all()


async def get_workflow(db: AsyncSession, workflow_id: str) -> Optional[Workflow]:
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    return result.scalar_one_or_none()


async def create_workflow(db: AsyncSession, data: WorkflowCreate, org_id: str, user_id: str) -> Workflow:
    workflow = Workflow(
        org_id=org_id,
        name=data.name,
        template_slug=data.template_slug,
        graph_definition=data.graph_definition,
        created_by=user_id,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow


async def update_workflow(db: AsyncSession, workflow: Workflow, data: WorkflowUpdate) -> Workflow:
    if workflow.status == "active":
        raise ValueError("Cannot update an active workflow — pause it first")
    if data.name is not None:
        workflow.name = data.name
    if data.graph_definition is not None:
        workflow.graph_definition = data.graph_definition

    await db.commit()
    await db.refresh(workflow)
    return workflow


async def delete_workflow(db: AsyncSession, workflow: Workflow) -> None:
    if workflow.status != "draft":
        raise ValueError("Can only delete workflows in draft status")
    await db.delete(workflow)
    await db.commit()


def validate_workflow_graph(graph_def: dict) -> list[str]:
    """Return a list of human-readable error strings; empty list means valid."""
    errors: list[str] = []
    nodes: list[dict] = graph_def.get("nodes", [])
    edges: list[dict] = graph_def.get("edges", [])

    if not nodes:
        errors.append("Add at least one agent node to the canvas")
        return errors  # nothing else to check

    for node in nodes:
        data = node.get("data", {})
        label = data.get("agentName") or data.get("label") or node.get("id", "Node")
        if not data.get("agentId"):
            errors.append(
                f'"{label}" has no agent assigned — open its config panel and save an agent'
            )

    for edge in edges:
        data = edge.get("data", {})
        if not data.get("event"):
            src_id = edge.get("source", "?")
            tgt_id = edge.get("target", "?")
            src_label = next(
                (
                    (n.get("data", {}).get("agentName") or n.get("data", {}).get("label", src_id))
                    for n in nodes
                    if n.get("id") == src_id
                ),
                src_id,
            )
            tgt_label = next(
                (
                    (n.get("data", {}).get("agentName") or n.get("data", {}).get("label", tgt_id))
                    for n in nodes
                    if n.get("id") == tgt_id
                ),
                tgt_id,
            )
            errors.append(
                f'Connection from "{src_label}" → "{tgt_label}" has no trigger event selected'
            )

    return errors


async def _build_agent_db_configs(db: AsyncSession, graph_def: dict) -> dict:
    """Build the agent_db_configs dict needed by GraphWorkflowInput.

    Scans all nodes in the graph, fetches the Agent row and its tool configs
    from the DB, and returns::

        {
            "<agent_db_id>": {
                "config": {...},          # agents.config JSON
                "tool_config": {...},     # agent_tool_configs.config (gmail / first tool)
            },
            ...
        }
    """
    from sqlalchemy.orm import selectinload

    nodes: list[dict] = graph_def.get("nodes", [])
    agent_ids = [
        n.get("data", {}).get("agentId")
        for n in nodes
        if n.get("data", {}).get("agentId")
    ]
    if not agent_ids:
        return {}

    from db.models import Agent as AgentModel

    result = await db.execute(
        select(AgentModel)
        .options(selectinload(AgentModel.tool_configs))
        .where(AgentModel.id.in_(agent_ids))
    )
    agents = result.scalars().all()

    agent_db_configs: dict = {}
    for agent in agents:
        # Pick the first tool config (usually "gmail") if any
        tool_config: dict = {}
        if agent.tool_configs:
            # Prefer a tool named "gmail"; otherwise take the first one
            gmail_cfg = next(
                (tc.config for tc in agent.tool_configs if tc.name == "gmail"),
                agent.tool_configs[0].config if agent.tool_configs else {},
            )
            tool_config = gmail_cfg or {}

        agent_db_configs[agent.id] = {
            "config": agent.config or {},
            "tool_config": tool_config,
        }

    return agent_db_configs


async def deploy_workflow(db: AsyncSession, workflow: Workflow) -> dict:
    errors = validate_workflow_graph(workflow.graph_definition)
    if errors:
        raise ValueError("Workflow is not valid: " + "; ".join(errors))

    compiled = compile_graph(workflow.graph_definition)

    # Build agent credential map for Temporal
    agent_db_configs = await _build_agent_db_configs(db, workflow.graph_definition)

    temporal_id = await start_workflow(workflow.id, compiled, agent_db_configs)
    workflow.compiled_graph = compiled
    workflow.temporal_workflow_id = temporal_id
    workflow.status = "active"
    await db.commit()
    await db.refresh(workflow)
    return {"status": workflow.status, "temporal_workflow_id": workflow.temporal_workflow_id}


async def pause_workflow_action(db: AsyncSession, workflow: Workflow) -> dict:
    if workflow.temporal_workflow_id:
        await pause_workflow(workflow.temporal_workflow_id)
    workflow.status = "paused"
    await db.commit()
    return {"status": "paused"}


async def resume_workflow_action(db: AsyncSession, workflow: Workflow) -> dict:
    workflow.status = "active"
    await db.commit()
    return {"status": "active"}


def get_workflow_templates() -> list[dict]:
    return WORKFLOW_TEMPLATES


def get_workflow_template(slug: str) -> Optional[dict]:
    return next((t for t in WORKFLOW_TEMPLATES if t["slug"] == slug), None)
