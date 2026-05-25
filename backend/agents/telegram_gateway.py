"""Telegram Gateway agent — sends and receives messages via a Telegram bot.

Events emitted:
  - message.received  {chat_id, text, user_id}
  - message.sent      {chat_id, message_id}

Phase 2: runs python-telegram-bot in a Temporal Activity with long polling.
"""

from agents.base import BaseAgent


class TelegramGatewayAgent(BaseAgent):
    """Channel agent that bridges Telegram messages into the workflow."""

    agent_type = "telegram_gateway"

    async def run(self, event_name: str, payload: dict) -> dict:
        """Phase 2: receive or send a Telegram message via the configured bot."""
        return {}
