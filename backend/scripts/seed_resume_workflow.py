"""Seed the Resume Processing Pipeline workflow.

Creates:
  1. Four agents in the DB (watcher, pdf_parser, assignment_generator, sender)
  2. Copies Gmail credential from existing weather pipeline watcher
  3. Inserts the Workflow graph
  4. Starts the Temporal workflow

Run with:
    cd backend && .venv/bin/python scripts/seed_resume_workflow.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa
from uuid import uuid4
from db.base import AsyncSessionLocal
from db.models import Agent, AgentToolConfig, Workflow


ORG_ID = "dev-org-id"
USER_ID = "dev-user-id"
WORKFLOW_NAME = "Resume Processing Pipeline"
WORKFLOW_ID = str(uuid4())


async def get_gmail_credential(session) -> dict:
    """Copy the Gmail credential from the existing weather pipeline watcher."""
    rows = await session.execute(sa.text("""
        SELECT atc.config
        FROM agent_tool_configs atc
        JOIN agents a ON a.id = atc.agent_id
        WHERE atc.name = 'gmail' AND a.type = 'gmail_watcher'
        LIMIT 1
    """))
    row = rows.fetchone()
    if not row:
        raise RuntimeError("No Gmail credential found — run the weather pipeline OAuth first.")
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


async def seed():
    async with AsyncSessionLocal() as session:
        # Check if workflow already exists
        existing = await session.execute(
            sa.select(Workflow).where(Workflow.name == WORKFLOW_NAME)
        )
        if existing.scalar_one_or_none():
            print(f"Workflow '{WORKFLOW_NAME}' already exists — skipping seed.")
            return

        gmail_cred = await get_gmail_credential(session)
        print(f"Got Gmail credential for: {gmail_cred.get('gmail_address')}")

        # ── Node IDs ──────────────────────────────────────────────────────
        watcher_id = str(uuid4())
        parser_id = str(uuid4())
        gen_id = str(uuid4())
        sender_id = str(uuid4())

        node_watcher = "node-resume-watcher"
        node_parser = "node-resume-parser"
        node_gen = "node-resume-gen"
        node_sender = "node-resume-sender"

        # ── Agents ────────────────────────────────────────────────────────
        watcher = Agent(
            id=watcher_id,
            org_id=ORG_ID,
            workflow_id=WORKFLOW_ID,
            name="Resume Gmail Watcher",
            type="gmail_watcher",
            config={
                "label_filter": "INBOX",
                "sender_filter": "",
                "subject_filter": "",
                "has_attachment": True,
                "filename_filter": "pdf",
                "fetch_attachments": True,
                "poll_interval": 30,
            },
            is_active=True,
            created_by=USER_ID,
        )

        parser = Agent(
            id=parser_id,
            org_id=ORG_ID,
            workflow_id=WORKFLOW_ID,
            name="Resume PDF Parser",
            type="pdf_parser",
            config={},
            is_active=True,
            created_by=USER_ID,
        )

        gen = Agent(
            id=gen_id,
            org_id=ORG_ID,
            workflow_id=WORKFLOW_ID,
            name="Assignment Generator",
            type="assignment_generator",
            config={
                "company_name": "Agent Platform",
                "role": "Senior Software Engineer",
            },
            is_active=True,
            created_by=USER_ID,
        )

        sender = Agent(
            id=sender_id,
            org_id=ORG_ID,
            workflow_id=WORKFLOW_ID,
            name="Assignment Email Sender",
            type="gmail_sender",
            config={},   # to_email comes dynamically from assignment_generator payload
            is_active=True,
            created_by=USER_ID,
        )

        session.add_all([watcher, parser, gen, sender])

        # ── Tool configs (Gmail credential on watcher + sender) ───────────
        session.add(AgentToolConfig(
            id=str(uuid4()),
            agent_id=watcher_id,
            name="gmail",
            kind="tool",
            config=gmail_cred,
        ))
        session.add(AgentToolConfig(
            id=str(uuid4()),
            agent_id=sender_id,
            name="gmail",
            kind="tool",
            config=gmail_cred,
        ))

        # ── Workflow graph ────────────────────────────────────────────────
        graph = {
            "nodes": [
                {
                    "id": node_watcher,
                    "type": "agentNode",
                    "position": {"x": 100, "y": 200},
                    "data": {
                        "label": "Resume Gmail Watcher",
                        "agentType": "gmail_watcher",
                        "agentId": watcher_id,
                        "isLongRunning": True,
                    },
                },
                {
                    "id": node_parser,
                    "type": "agentNode",
                    "position": {"x": 400, "y": 200},
                    "data": {
                        "label": "PDF Parser",
                        "agentType": "pdf_parser",
                        "agentId": parser_id,
                        "isLongRunning": False,
                    },
                },
                {
                    "id": node_gen,
                    "type": "agentNode",
                    "position": {"x": 700, "y": 200},
                    "data": {
                        "label": "Assignment Generator",
                        "agentType": "assignment_generator",
                        "agentId": gen_id,
                        "isLongRunning": False,
                    },
                },
                {
                    "id": node_sender,
                    "type": "agentNode",
                    "position": {"x": 1000, "y": 200},
                    "data": {
                        "label": "Assignment Email Sender",
                        "agentType": "gmail_sender",
                        "agentId": sender_id,
                        "isLongRunning": False,
                    },
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": node_watcher,
                    "target": node_parser,
                    "data": {"event": "gmail_watcher.email.received"},
                },
                {
                    "id": "e2",
                    "source": node_parser,
                    "target": node_gen,
                    "data": {"event": "pdf_parser.resume.parsed"},
                },
                {
                    "id": "e3",
                    "source": node_gen,
                    "target": node_sender,
                    "data": {"event": "assignment_generator.assignment.ready"},
                },
            ],
        }

        workflow = Workflow(
            id=WORKFLOW_ID,
            org_id=ORG_ID,
            name=WORKFLOW_NAME,
            template_slug="resume_pipeline",
            graph_definition=graph,
            compiled_graph={"compiled": True, "topology": graph},
            status="active",
            created_by=USER_ID,
        )
        session.add(workflow)
        await session.commit()
        print(f"Created workflow: {WORKFLOW_NAME} ({WORKFLOW_ID})")

        # ── Build agent_db_configs for Temporal ───────────────────────────
        agent_db_configs = {
            watcher_id: {
                "config": watcher.config,
                "tool_config": gmail_cred,
            },
            parser_id: {
                "config": parser.config,
                "tool_config": {},
            },
            gen_id: {
                "config": gen.config,
                "tool_config": {},
            },
            sender_id: {
                "config": sender.config,
                "tool_config": gmail_cred,
            },
        }

    # ── Start Temporal workflow ───────────────────────────────────────────
    from runtime.temporal_client import start_workflow as temporal_start

    temporal_wf_id = f"platform-workflow-{WORKFLOW_ID}"

    try:
        await temporal_start(
            workflow_id=WORKFLOW_ID,
            compiled_graph={"topology": graph},
            agent_db_configs=agent_db_configs,
        )
        print(f"Temporal workflow started: {temporal_wf_id}")
    except Exception as exc:
        print(f"Temporal start failed (may already be running): {exc}")

    # ── Persist temporal_workflow_id ──────────────────────────────────────
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa.text("UPDATE workflows SET temporal_workflow_id = :tid, status = 'active' WHERE id = :id"),
            {"tid": temporal_wf_id, "id": WORKFLOW_ID},
        )
        await session.commit()

    print("\nDone! Resume Processing Pipeline is live.")
    print(f"Send an email to vivekbalachandra@gmail.com with a PDF resume attached.")
    print(f"The pipeline will parse it and email a tailored assignment to the candidate.")


if __name__ == "__main__":
    asyncio.run(seed())
