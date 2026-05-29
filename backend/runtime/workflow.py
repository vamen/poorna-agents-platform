"""Temporal workflow and activities for executing a platform workflow graph.

Architecture
------------
One Temporal workflow (``GraphWorkflow``) is started per deployed platform
workflow.  It interprets the compiled graph definition at runtime:

  1. Finds the trigger node (long-running, e.g. gmail_watcher).
  2. Runs a polling loop — every ``poll_interval`` seconds it calls the
     ``poll_trigger_activity`` activity which talks to Gmail and returns
     any new matching emails.
  3. For each incoming event it calls ``create_session_activity`` to open a
     WorkflowSession, then routes the event through ``run_node_activity`` for
     each downstream node in topological order.
  4. Every agent-to-agent hop is wrapped in NodeWrapper which persists a
     StandardMessage to agent_messages before calling the agent.
  5. Continues until the workflow is cancelled (paused/deleted).

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
class CreateSessionInput:
    workflow_id: str
    trigger_event: str
    correlation_id: str   # e.g. Gmail message_id — used for idempotency


@dataclass
class RunNodeInput:
    agent_type: str
    agent_config: dict
    tool_config: dict          # credential blob (may be empty for non-gmail agents)
    event_name: str
    payload: dict
    session_id: str = ""       # WorkflowSession ID for this run
    workflow_id: str = ""      # platform workflow DB id
    from_agent_id: str = ""    # sender agent DB id
    to_agent_id: str = ""      # receiver agent DB id


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
    """Poll a long-running trigger agent for new events.

    Cursor state is stored in agent_state keyed by the agent's declared
    ``poll_cursor_key`` (default "last_internal_date") so the activity is
    agent-agnostic.  The cursor value is the max of the payload field named
    by ``poll_cursor_payload_field`` across the returned events.

    GmailWatcher  → cursor_key="last_internal_date", payload_field="internal_date"
    TelegramWatcher → cursor_key="last_update_id",    payload_field="update_id"
    """
    from agents import instantiate_agent
    from services.agent_state_service import get_state, set_state

    agent = instantiate_agent(inp.agent_type, inp.agent_config)

    # Agents can declare their cursor key; default to gmail-style
    cursor_key: str = getattr(agent, "poll_cursor_key", "last_internal_date")
    cursor_payload_field: str = getattr(agent, "poll_cursor_payload_field", "internal_date")

    cursor: int = await get_state(
        inp.agent_id, inp.workflow_id, cursor_key, default=0
    )

    if hasattr(agent, "poll"):
        events = await agent.poll(
            inp.tool_config.get("credential", {}),
            cursor,
        )
    else:
        events = []

    if events:
        new_cursor = max(
            e.get("payload", {}).get(cursor_payload_field, 0) for e in events
        )
        if new_cursor > cursor:
            await set_state(inp.agent_id, inp.workflow_id, cursor_key, new_cursor)

    return PollOutput(events=events)


@activity.defn
async def create_session_activity(inp: CreateSessionInput) -> str:
    """Create (or return existing) WorkflowSession for one trigger event run.

    Called once per trigger event before any node activities run, so all
    downstream agent messages share the same session_id.
    """
    from services.message_service import get_or_create_session

    return await get_or_create_session(
        workflow_id=inp.workflow_id,
        trigger_event=inp.trigger_event,
        correlation_id=inp.correlation_id,
    )


@activity.defn
async def run_node_activity(inp: RunNodeInput) -> RunNodeOutput:
    """Execute a single-shot agent node via NodeWrapper and return its output.

    NodeWrapper persists a StandardMessage to agent_messages before calling
    agent.run(), and updates the message status after.
    """
    from agents import instantiate_agent
    from agents.node_wrapper import NodeWrapper
    from agents.standard_message import StandardMessage, Sender, Recipient

    # Build agent config with injected credentials
    config = dict(inp.agent_config)
    if inp.tool_config:
        config["_credential"] = inp.tool_config.get("credential", {})
        config["_gmail_address"] = inp.tool_config.get("gmail_address", "")
    # Inject session_id so strategies can fetch conversation history
    if inp.session_id:
        config["_session_id"] = inp.session_id
    # Inject agent_id so strategies can persist assistant messages
    if inp.to_agent_id:
        config["_agent_id"] = inp.to_agent_id

    agent = instantiate_agent(inp.agent_type, config)

    message = StandardMessage(
        session_id=inp.session_id,
        workflow_id=inp.workflow_id,
        sender=Sender(type="agent", ref_id=inp.from_agent_id),
        recipient=Recipient(type="agent", ref_id=inp.to_agent_id),
        event_name=inp.event_name,
        payload=inp.payload,
    )

    result = await NodeWrapper(agent).run(message)

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

        node_by_id = {n["id"]: n for n in nodes}
        edges_from: dict[str, list[dict]] = {}
        for e in edges:
            edges_from.setdefault(e["source"], []).append(e)

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

            for event in poll_out.events:
                # One session per trigger event — correlation_id = Gmail message_id
                correlation_id = event.get("payload", {}).get("message_id", "")
                session_id: str = await workflow.execute_activity(
                    create_session_activity,
                    CreateSessionInput(
                        workflow_id=inp.workflow_id,
                        trigger_event=event["event"],
                        correlation_id=correlation_id,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )

                await self._route_event(
                    event_name=event["event"],
                    payload=event["payload"],
                    source_node_id=trigger_node["id"],
                    source_agent_id=trigger_agent_db_id,
                    node_by_id=node_by_id,
                    edges_from=edges_from,
                    agent_db_configs=inp.agent_db_configs,
                    workflow_id=inp.workflow_id,
                    session_id=session_id,
                )

            await workflow.sleep(timedelta(seconds=inp.poll_interval))

    async def _route_event(
        self,
        event_name: str,
        payload: dict,
        source_node_id: str,
        source_agent_id: str,
        node_by_id: dict,
        edges_from: dict,
        agent_db_configs: dict,
        workflow_id: str,
        session_id: str,
    ) -> None:
        """Fan out an event to all matching downstream nodes."""
        outgoing = edges_from.get(source_node_id, [])

        for edge in outgoing:
            edge_data = edge.get("data", {}) or {}
            required_event = edge_data.get("event", "")

            if required_event and required_event != event_name:
                continue

            expr = (edge_data.get("filter") or "").strip()
            if expr:
                try:
                    if not eval(expr, {}, {"payload": payload}):  # noqa: S307
                        continue
                except Exception as exc:
                    workflow.logger.warning("Filter eval error: %s", exc)
                    continue

            target_id = edge["target"]
            target_node = node_by_id.get(target_id)
            if not target_node:
                continue

            target_data = target_node.get("data", {})
            target_agent_db_id = target_data.get("agentId", "")
            target_agent_type = target_data.get("agentType", "")
            target_cfg = agent_db_configs.get(target_agent_db_id, {})

            workflow.logger.info(
                "Dispatching %s → node %s (%s)  session=%s",
                event_name, target_id, target_agent_type, session_id[:8],
            )

            node_out: RunNodeOutput = await workflow.execute_activity(
                run_node_activity,
                RunNodeInput(
                    agent_type=target_agent_type,
                    agent_config=target_cfg.get("config", {}),
                    tool_config=target_cfg.get("tool_config", {}),
                    event_name=event_name,
                    payload=payload,
                    session_id=session_id,
                    workflow_id=workflow_id,
                    from_agent_id=source_agent_id,
                    to_agent_id=target_agent_db_id,
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )

            if node_out.event_name:
                await self._route_event(
                    event_name=node_out.event_name,
                    payload=node_out.payload,
                    source_node_id=target_id,
                    source_agent_id=target_agent_db_id,
                    node_by_id=node_by_id,
                    edges_from=edges_from,
                    agent_db_configs=agent_db_configs,
                    workflow_id=workflow_id,
                    session_id=session_id,
                )
