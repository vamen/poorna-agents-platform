"""Temporal client helpers for starting/pausing/resuming platform workflows."""

from __future__ import annotations

import logging
from datetime import timedelta

from temporalio.client import Client

from config import settings

logger = logging.getLogger(__name__)

TASK_QUEUE = "workflow-graph-queue"


async def _get_client() -> Client:
    return await Client.connect(settings.temporal_host)


async def start_workflow(
    workflow_id: str,
    compiled_graph: dict,
    agent_db_configs: dict | None = None,
) -> str:
    """Start a Temporal GraphWorkflow for the given platform workflow.

    Parameters
    ----------
    workflow_id:
        The platform workflow DB id (UUID string).
    compiled_graph:
        The compiled graph dict returned by ``compile_graph()``.  The raw
        graph topology is under ``compiled_graph["topology"]``; if the key is
        missing the whole dict is used as the graph definition.
    agent_db_configs:
        ``{agent_db_id: {"config": {...}, "tool_config": {...}}}`` — built by
        ``deploy_workflow()`` in workflow_service.py.
    """
    from runtime.workflow import GraphWorkflow, GraphWorkflowInput

    graph_definition = compiled_graph.get("topology", compiled_graph)

    client = await _get_client()

    inp = GraphWorkflowInput(
        workflow_id=workflow_id,
        graph_definition=graph_definition,
        agent_db_configs=agent_db_configs or {},
        poll_interval=30,
    )

    temporal_wf_id = f"platform-workflow-{workflow_id}"

    handle = await client.start_workflow(
        GraphWorkflow.run,
        inp,
        id=temporal_wf_id,
        task_queue=TASK_QUEUE,
        execution_timeout=timedelta(days=365),
    )
    logger.info(
        "Started Temporal workflow %s for platform workflow %s",
        handle.id,
        workflow_id,
    )
    return handle.id


async def pause_workflow(temporal_workflow_id: str) -> bool:
    """Cancel the running Temporal workflow (effectively pausing the platform workflow)."""
    try:
        client = await _get_client()
        handle = client.get_workflow_handle(temporal_workflow_id)
        await handle.cancel()
        logger.info("Cancelled Temporal workflow %s", temporal_workflow_id)
        return True
    except Exception as exc:
        logger.error(
            "Failed to cancel Temporal workflow %s: %s", temporal_workflow_id, exc
        )
        return False


async def resume_workflow(temporal_workflow_id: str) -> bool:
    """Re-start a previously paused workflow.

    Temporal doesn't have a native pause/resume for a cancelled workflow —
    the workflow service re-calls ``start_workflow`` with the same ID.
    This function is a no-op placeholder kept for API symmetry.
    """
    logger.info(
        "resume_workflow called for %s — caller should re-deploy the workflow",
        temporal_workflow_id,
    )
    return True
