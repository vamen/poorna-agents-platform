"""Telegram reply tool — sends a message to a Telegram chat via Bot API.

Credentials expected in creds dict:
  bot_token     — Telegram bot token from @BotFather
  _session_id   — injected by ReactExecutor for message persistence
  _agent_id     — injected by ReactExecutor for message persistence
"""

from __future__ import annotations

import logging
import uuid

import httpx

from tools.base import BaseTool

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramReplyTool(BaseTool):
    name = "send_telegram"
    description = (
        "Send a text message to a Telegram chat. "
        "Use this to reply to the user or send notifications."
    )
    input_schema = {
        "type": "object",
        "required": ["chat_id", "text"],
        "properties": {
            "chat_id": {
                "type": "string",
                "description": "Telegram chat ID (number as string) to send the message to.",
            },
            "text": {
                "type": "string",
                "description": "The message text. Supports Markdown.",
            },
            "parse_mode": {
                "type": "string",
                "enum": ["Markdown", "HTML", ""],
                "description": "Optional formatting mode.",
            },
        },
    }

    async def execute(self, input: dict, creds: dict) -> dict:
        # creds is the full tool_config blob {"credential": {...}}
        c = creds.get("credential", creds)
        bot_token = c.get("bot_token", "")
        url = _TELEGRAM_API.format(token=bot_token)

        body: dict = {
            "chat_id": input["chat_id"],
            "text": input["text"],
        }
        if parse_mode := input.get("parse_mode"):
            body["parse_mode"] = parse_mode

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, timeout=15)
            resp.raise_for_status()
            data = resp.json()

        message_id = data.get("result", {}).get("message_id")
        logger.info("TelegramReplyTool: sent message_id=%s to chat=%s", message_id, input["chat_id"])

        # Persist this outbound message as an agent_message so the react
        # executor can include it in conversation history on the next turn.
        await _persist_outbound_message(
            session_id=creds.get("_session_id", ""),
            agent_id=creds.get("_agent_id", ""),
            chat_id=str(input["chat_id"]),
            text=input["text"],
        )

        return {"ok": True, "message_id": message_id}


async def _persist_outbound_message(
    session_id: str, agent_id: str, chat_id: str, text: str
) -> None:
    """Save the outbound Telegram message to agent_messages.

    sender  = the react agent (type=agent,  ref_id=agent_id)
    recipient = the Telegram user (type=telegram_user, ref_id=chat_id)
    """
    if not session_id or not agent_id:
        return
    try:
        import sqlalchemy as sa
        from db.base import AsyncSessionLocal
        from db.models import AgentMessage, Sender, Recipient

        async with AsyncSessionLocal() as db:
            # Upsert sender row for the agent
            res = await db.execute(
                sa.select(Sender).where(
                    Sender.type == "agent",
                    Sender.ref_id == agent_id,
                )
            )
            sender_row = res.scalar_one_or_none()
            if not sender_row:
                sender_row = Sender(type="agent", ref_id=agent_id, display_name="agent")
                db.add(sender_row)
                await db.flush()

            # Upsert recipient row for the Telegram user
            res = await db.execute(
                sa.select(Recipient).where(
                    Recipient.type == "telegram_user",
                    Recipient.ref_id == chat_id,
                )
            )
            recipient_row = res.scalar_one_or_none()
            if not recipient_row:
                recipient_row = Recipient(
                    type="telegram_user", ref_id=chat_id, display_name=f"tg:{chat_id}"
                )
                db.add(recipient_row)
                await db.flush()

            msg = AgentMessage(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sender_id=sender_row.id,
                recipient_id=recipient_row.id,
                event_name="send_telegram",
                payload={"text": text, "chat_id": chat_id},
                status="delivered",
            )
            db.add(msg)
            await db.commit()
            logger.debug(
                "TelegramReplyTool: saved outbound message to agent_messages session=%s",
                session_id,
            )
    except Exception as exc:
        logger.warning("TelegramReplyTool: failed to persist message: %s", exc)


tool = TelegramReplyTool()
