"""TelegramWatcherAgent — polls Telegram getUpdates for messages from a bot.

Runs as a Temporal long-running trigger (isLongRunning=true).  On each poll
tick it calls getUpdates with an offset cursor so it never replays old messages.

Config (set in the canvas / agent_tool_configs):
    bot_token      — Telegram bot token from @BotFather  (required, from tool_config)
    allowed_user_id — optional int; if set, only messages from this user are processed
    context_messages — how many prior messages to include in the payload (default 5)

Events emitted:
    telegram_watcher.message.received  {
        update_id, chat_id, user_id, username, text,
        file_refs: [FileRef.to_dict(), ...],   # photos / documents
        conversation: [{role, text}, ...]      # last N messages from this chat
    }
"""

from __future__ import annotations

import logging

import httpx

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

_TG_BASE = "https://api.telegram.org/bot{token}"


class TelegramWatcherAgent(BaseAgent):
    agent_type = "telegram_watcher"
    poll_cursor_key = "last_update_id"
    poll_cursor_payload_field = "update_id"

    async def poll(self, credential: dict, last_update_id: int = 0) -> list[dict]:
        """Poll getUpdates and return new message events.

        *credential* comes from the agent's tool_config (bot_token lives there).
        *last_update_id* is persisted in agent_state between ticks.
        """
        # credential blob is {"credential": {"bot_token": "..."}} from agent_tool_configs
        cred = credential.get("credential", credential)
        bot_token = cred.get("bot_token", "")
        if not bot_token:
            logger.error("TelegramWatcher: no bot_token in credential — skipping")
            return []

        base = _TG_BASE.format(token=bot_token)
        params: dict = {"timeout": 0, "allowed_updates": ["message"]}
        if last_update_id > 0:
            params["offset"] = last_update_id + 1

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{base}/getUpdates", params=params, timeout=30)
                resp.raise_for_status()
            except Exception as exc:
                logger.error("TelegramWatcher: getUpdates failed: %s", exc)
                return []

        data = resp.json()
        updates = data.get("result", [])

        allowed_user = self.config.get("allowed_user_id")
        if allowed_user is not None:
            allowed_user = int(allowed_user)

        context_n: int = int(self.config.get("context_messages", 5))

        events: list[dict] = []
        for upd in updates:
            msg = upd.get("message")
            if not msg:
                continue

            from_user = msg.get("from", {})
            user_id: int = from_user.get("id", 0)

            if allowed_user is not None and user_id != allowed_user:
                continue

            chat_id: int = msg.get("chat", {}).get("id", 0)
            text: str = msg.get("text", "")
            update_id: int = upd["update_id"]
            username: str = from_user.get("username", "")

            # Handle file attachments (photo, document)
            file_refs = await _extract_file_refs(msg, base)

            # Fetch conversation context from DB
            conversation = await _load_conversation(
                str(chat_id), context_n
            )

            events.append({
                "event": "telegram_watcher.message.received",
                "payload": {
                    "update_id": update_id,
                    "chat_id": str(chat_id),
                    "user_id": str(user_id),
                    "username": username,
                    "text": text,
                    "file_refs": file_refs,
                    "conversation": conversation,
                },
            })

        logger.info("TelegramWatcher: %d new messages", len(events))
        return events

    async def run(self, event_name: str, payload: dict) -> dict:
        """Not used directly — agent runs via poll() in the Temporal worker."""
        return {}


async def _extract_file_refs(msg: dict, base_url: str) -> list[dict]:
    """Download any attached photo/document and store via FileService."""
    from agents.file_ref import FileRef
    from services.file_service import FileService

    file_refs: list[dict] = []

    # Photos — take the largest resolution
    photos = msg.get("photo", [])
    if photos:
        best = max(photos, key=lambda p: p.get("file_size", 0))
        ref = await _download_telegram_file(best["file_id"], base_url, "image.jpg", "image/jpeg")
        if ref:
            file_refs.append(ref.to_dict())

    # Documents
    doc = msg.get("document")
    if doc:
        mime = doc.get("mime_type", "application/octet-stream")
        fname = doc.get("file_name", "document")
        ref = await _download_telegram_file(doc["file_id"], base_url, fname, mime)
        if ref:
            file_refs.append(ref.to_dict())

    return file_refs


async def _download_telegram_file(file_id: str, base_url: str, filename: str, mime: str):
    """Download a Telegram file by file_id and store it in FileService."""
    from services.file_service import FileService

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{base_url}/getFile", params={"file_id": file_id}, timeout=15)
            resp.raise_for_status()
            file_path = resp.json().get("result", {}).get("file_path", "")
            if not file_path:
                return None

            # Extract the token from base_url
            token = base_url.split("/bot")[1]
            file_resp = await client.get(
                f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=30
            )
            file_resp.raise_for_status()
            data = file_resp.content
        except Exception as exc:
            logger.warning("TelegramWatcher: file download failed for %s: %s", file_id, exc)
            return None

    return await FileService.put(data, filename=filename, mime_type=mime)


async def _load_conversation(chat_id: str, n: int) -> list[dict]:
    """Load the last *n* messages from this chat_id out of agent_messages."""
    import sqlalchemy as sa
    from db.base import AsyncSessionLocal
    from db.models import AgentMessage, Sender as SenderModel, Recipient as RecipientModel

    async with AsyncSessionLocal() as db:
        # Find sender rows with ref_id == chat_id (telegram_user type)
        result = await db.execute(
            sa.select(AgentMessage)
            .join(SenderModel, AgentMessage.sender_id == SenderModel.id)
            .where(SenderModel.ref_id == chat_id)
            .order_by(AgentMessage.created_at.desc())
            .limit(n)
        )
        rows = result.scalars().all()

    conversation: list[dict] = []
    for row in reversed(rows):  # chronological order
        payload = row.payload or {}
        conversation.append({
            "role": "user",
            "text": payload.get("text", ""),
        })

    return conversation
