"""Temporal worker — registers activities and workflows.

Run with:
    cd backend && .venv/bin/python -m runtime.worker

The worker connects to the Temporal server at TEMPORAL_HOST (default
localhost:7233) and processes tasks from the 'workflow-graph-queue' task queue.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os

# Ensure the backend directory is on the path when running as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from temporalio.client import Client
from temporalio.worker import Worker

from config import settings
from runtime.workflow import (
    GraphWorkflow,
    poll_trigger_activity,
    create_session_activity,
    run_node_activity,
)

logger = logging.getLogger(__name__)

TASK_QUEUE = "workflow-graph-queue"


async def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    # Suppress noisy debug logs from third-party libs
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "temporalio"):
        logging.getLogger(noisy).setLevel(logging.INFO)
    logger.info("Connecting to Temporal at %s", settings.temporal_host)

    client = await Client.connect(settings.temporal_host)

    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[GraphWorkflow],
        activities=[poll_trigger_activity, create_session_activity, run_node_activity],
    ):
        logger.info("Worker started on queue '%s' — waiting for tasks…", TASK_QUEUE)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
