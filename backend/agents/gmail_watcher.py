"""GmailWatcher agent — polls Gmail for matching emails.

Runs as a Temporal Activity (called every poll interval by the workflow).
Returns a list of matching emails as ``email.received`` events.

Config (from agent_tool_configs):
    gmail_address   — the authenticated Gmail address
    credential      — OAuth2 credential blob (access_token, refresh_token, …)

Agent config (from agent.config JSON blob, set in the canvas):
    sender_filter   — e.g. "vivekbalachandra@gmail.com"
    subject_filter  — e.g. "agent-platform-test"
    label_filter    — e.g. "INBOX" (default)
    poll_interval   — seconds between polls (default 30)
"""

from __future__ import annotations

import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class GmailWatcherAgent(BaseAgent):
    agent_type = "gmail_watcher"

    def _build_query(self, after_ts: int = 0) -> str:
        parts: list[str] = []
        label = self.config.get("label_filter", "INBOX")
        if label:
            parts.append(f"label:{label}")
        sender = self.config.get("sender_filter", "")
        if sender:
            parts.append(f"from:{sender}")
        subject = self.config.get("subject_filter", "")
        if subject:
            parts.append(f'subject:"{subject}"')
        if self.config.get("has_attachment"):
            parts.append("has:attachment")
        filename = self.config.get("filename_filter", "")
        if filename:
            parts.append(f"filename:{filename}")
        # Use timestamp cursor instead of is:unread to avoid Gmail read-state dependency
        if after_ts > 0:
            parts.append(f"after:{after_ts}")
        return " ".join(parts)

    async def poll(self, credential: dict, last_internal_date: int = 0) -> list[dict]:
        """Poll Gmail once, return messages newer than *last_internal_date* (ms epoch).

        Called by the Temporal activity on each timer tick.
        ``last_internal_date`` is the Gmail internalDate (ms) of the last processed message.
        The next call should pass the max internalDate returned from this call.
        """
        from runtime.gmail_client import get_gmail_service, list_messages, get_message

        try:
            service = get_gmail_service(credential)
        except Exception as exc:
            logger.error("GmailWatcher: auth failed: %s", exc)
            return []

        # Gmail after: filter uses Unix seconds
        after_ts_seconds = last_internal_date // 1000 if last_internal_date > 0 else 0
        query = self._build_query(after_ts=after_ts_seconds)
        logger.info("GmailWatcher polling: %s (cursor=%d)", query, last_internal_date)

        stubs = list_messages(service, query, max_results=10)
        events: list[dict] = []

        for stub in stubs:
            msg_id = stub["id"]
            msg = get_message(service, msg_id)
            if msg is None:
                continue

            msg_ts = msg.get("internal_date", 0)
            # Skip messages at or before the cursor (after: is inclusive at second boundary)
            if msg_ts <= last_internal_date:
                continue

            events.append({
                "event": "gmail_watcher.email.received",
                "payload": {
                    "message_id": msg["id"],
                    "thread_id": msg["thread_id"],
                    "subject": msg["subject"],
                    "sender": msg["sender"],
                    "to": msg["to"],
                    "body": msg["body"],
                    "snippet": msg["snippet"],
                    "attachments": msg.get("attachments", []),
                    "internal_date": msg_ts,
                },
            })

        logger.info("GmailWatcher: found %d new messages", len(events))
        return events

    async def run(self, event_name: str, payload: dict) -> dict:
        """Not used directly — agent runs via poll() in the Temporal worker."""
        return {}
