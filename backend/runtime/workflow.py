"""Temporal workflow and activities for executing a platform workflow graph.

Architecture
------------
One Temporal workflow (``GraphWorkflow``) is started per deployed platform
workflow.  It interprets the compiled graph definition at runtime:

  1. Finds the trigger node (long-running, e.g. gmail_watcher).
  2. Runs a polling loop — every ``poll_interval`` seconds it calls the
     ``poll_trigger_activity`` activity which talks to Gmail and returns
     any new matching emails.
  3. For each incoming event it calls ``run_node_activity`` for each
     downstream node in topological order, routing the event payload
     through the edge event/filter conditions.
  4. Continues until the workflow is cancelled (paused/deleted).

Activities are plain async functions decorated with ``@activity.defn``.
They receive serialisable dicts so Temporal can serialize them.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

logger = logging.getLogger(__name__)

NO_RETRY = RetryPolicy(maximum_attempts=1)


# ── Dataclasses for Temporal serialization ────────────────────────────────────

from dataclasses import dataclass, field


@dataclass
class PollInput:
    agent_type: str
    agent_config: dict   # agent instance config (sender_filter, etc.)
    tool_config: dict    # credential blob from agent_tool_configs
    agent_id: str        # DB id of this agent — used to key agent_state
    workflow_id: str     # DB id of parent workflow — used to key agent_state


@dataclass
class PollOutput:
    events: list[dict]


@dataclass
class RunNodeInput:
    agent_type: str
    agent_config: dict
    tool_config: dict   # credential blob (may be empty for non-gmail agents)
    event_name: str
    payload: dict


@dataclass
class RunNodeOutput:
    event_name: str   # e.g. "classification.done"
    payload: dict


@dataclass
class GraphWorkflowInput:
    workflow_id: str          # platform workflow DB id
    graph_definition: dict    # {nodes, edges}
    agent_db_configs: dict    # {agent_db_id: {config: {...}, tool_config: {...}}}
    poll_interval: int = 30   # seconds


# ── Activities ────────────────────────────────────────────────────────────────

@activity.defn
async def poll_trigger_activity(inp: PollInput) -> PollOutput:
    """Poll a long-running trigger agent (e.g. GmailWatcher) for new events.

    seen_ids are loaded from agent_state at the start of each poll and saved
    back after, so they survive worker restarts.
    """
    from agents import instantiate_agent
    from services.agent_state_service import get_state, set_state

    agent = instantiate_agent(inp.agent_type, inp.agent_config)

    # Load persisted seen_ids from DB (empty list on first run)
    seen_list: list[str] = await get_state(
        inp.agent_id, inp.workflow_id, "seen_ids", default=[]
    )
    seen = set(seen_list)

    if hasattr(agent, "poll"):
        events = await agent.poll(inp.tool_config.get("credential", {}), seen)
    else:
        events = []

    # Persist updated seen_ids back to DB
    await set_state(inp.agent_id, inp.workflow_id, "seen_ids", list(seen))

    return PollOutput(events=events)


@activity.defn
async def run_node_activity(inp: RunNodeInput) -> RunNodeOutput:
    """Execute a single-shot agent node and return its output event."""
    from agents import instantiate_agent

    # Inject credential into config so agents can access it
    config = dict(inp.agent_config)
    if inp.tool_config:
        config["_credential"] = inp.tool_config.get("credential", {})
        config["_gmail_address"] = inp.tool_config.get("gmail_address", "")

    agent = instantiate_agent(inp.agent_type, config)
    result = await agent.run(inp.event_name, inp.payload)

    return RunNodeOutput(
        event_name=result.get("event", ""),
        payload=result.get("payload", {}),
    )


# ── Workflow ──────────────────────────────────────────────────────────────────

@workflow.defn
class GraphWorkflow:
    """Temporal workflow that drives a platform workflow graph."""

    @workflow.run
    async def run(self, inp: GraphWorkflowInput) -> None:
        nodes: list[dict] = inp.graph_definition.get("nodes", [])
        edges: list[dict] = inp.graph_definition.get("edges", [])

        # Build lookup maps
        node_by_id = {n["id"]: n for n in nodes}
        # edges_from[node_id] → list of edges leaving that node
        edges_from: dict[str, list[dict]] = {}
        for e in edges:
            edges_from.setdefault(e["source"], []).append(e)

        # Find the trigger node (long-running)
        trigger_node = next(
            (n for n in nodes if n.get("data", {}).get("isLongRunning")),
            nodes[0] if nodes else None,
        )
        if not trigger_node:
            workflow.logger.error("No nodes in graph — exiting")
            return

        trigger_data = trigger_node.get("data", {})
        trigger_agent_db_id = trigger_data.get("agentId", "")
        trigger_agent_type = trigger_data.get("agentType", "")
        trigger_cfg = inp.agent_db_configs.get(trigger_agent_db_id, {})

        workflow.logger.info(
            "GraphWorkflow started — trigger=%s  poll_interval=%ds",
            trigger_agent_type, inp.poll_interval,
        )

        while True:
            # Poll the trigger (seen_ids are persisted in agent_state DB table)
            poll_out: PollOutput = await workflow.execute_activity(
                poll_trigger_activity,
                PollInput(
                    agent_type=trigger_agent_type,
                    agent_config=trigger_cfg.get("config", {}),
                    tool_config=trigger_cfg.get("tool_config", {}),
                    agent_id=trigger_agent_db_id,
                    workflow_id=inp.workflow_id,
                ),
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )

            # Process each incoming event through the graph
            for event in poll_out.events:
                await self._route_event(
                    event_name=event["event"],
                    payload=event["payload"],
                    source_node_id=trigger_node["id"],
                    node_by_id=node_by_id,
                    edges_from=edges_from,
                    agent_db_configs=inp.agent_db_configs,
                )

            # Wait before next poll (use workflow.sleep so Temporal can persist state)
            await workflow.sleep(timedelta(seconds=inp.poll_interval))

    async def _route_event(
        self,
        event_name: str,
        payload: dict,
        source_node_id: str,
        node_by_id: dict,
        edges_from: dict,
        agent_db_configs: dict,
    ) -> None:
        """Fan out an event to all matching downstream nodes."""
        outgoing = edges_from.get(source_node_id, [])

        for edge in outgoing:
            edge_data = edge.get("data", {}) or {}
            required_event = edge_data.get("event", "")

            # Event filter
            if required_event and required_event != event_name:
                continue

            # Expression filter (optional)
            expr = (edge_data.get("filter") or "").strip()
            if expr:
                try:
                    if not eval(expr, {}, {"payload": payload}):  # noqa: S307
                        continue
                except Exception as exc:
                    workflow.logger.warning("Filter eval error: %s", exc)
                    continue

            # Run the target node
            target_id = edge["target"]
            target_node = node_by_id.get(target_id)
            if not target_node:
                continue

            target_data = target_node.get("data", {})
            target_agent_db_id = target_data.get("agentId", "")
            target_agent_type = target_data.get("agentType", "")
            target_cfg = agent_db_configs.get(target_agent_db_id, {})

            workflow.logger.info(
                "Dispatching %s → node %s (%s)",
                event_name, target_id, target_agent_type,
            )

            node_out: RunNodeOutput = await workflow.execute_activity(
                run_node_activity,
                RunNodeInput(
                    agent_type=target_agent_type,
                    agent_config=target_cfg.get("config", {}),
                    tool_config=target_cfg.get("tool_config", {}),
                    event_name=event_name,
                    payload=payload,
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            # Recurse for the next layer
            if node_out.event_name:
                await self._route_event(
                    event_name=node_out.event_name,
                    payload=node_out.payload,
                    source_node_id=target_id,
                    node_by_id=node_by_id,
                    edges_from=edges_from,
                    agent_db_configs=agent_db_configs,
                )
