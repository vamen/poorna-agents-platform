"""NodeWrapper — persists a StandardMessage then delegates to the agent.

Usage (Temporal activity)::

    agent = instantiate_agent(agent_type, config)
    result = await NodeWrapper(agent).run(message)

Usage (chat / other contexts)::

    agent = TelegramResponderAgent(config)
    result = await NodeWrapper(agent).run(
        StandardMessage(
            session_id=session_id,
            workflow_id=workflow_id,
            sender=Sender(type="telegram_user", ref_id=chat_id),
            recipient=Recipient(type="agent", ref_id=responder_agent_id),
            event_name="telegram.message.received",
            payload={"text": "...", "chat_id": "..."},
        )
    )

The wrapper is intentionally thin — it owns persistence only.  All routing,
session creation, and LLM concerns live outside it.
"""

from __future__ import annotations

import logging

from agents.base import BaseAgent
from agents.standard_message import StandardMessage

logger = logging.getLogger(__name__)


class NodeWrapper:
    def __init__(self, agent: BaseAgent) -> None:
        self.agent = agent

    async def run(self, message: StandardMessage) -> dict:
        """Persist *message*, run the agent, update status, return result."""
        from services.message_service import save_message, update_message_status

        await save_message(message)
        logger.debug(
            "NodeWrapper: %s(%s) → %s(%s)  event=%s  msg=%s",
            message.sender.type, message.sender.ref_id[:8],
            message.recipient.type, message.recipient.ref_id[:8],
            message.event_name,
            message.message_id[:8],
        )

        try:
            result = await self.agent.run(message.event_name, message.payload)
            await update_message_status(message.message_id, "delivered")
            return result
        except Exception as exc:
            await update_message_status(message.message_id, "failed")
            logger.error(
                "NodeWrapper: agent %s failed for msg %s: %s",
                message.recipient.ref_id[:8], message.message_id[:8], exc,
            )
            raise
