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

    def _build_query(self) -> str:
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
        parts.append("is:unread")
        return " ".join(parts)

    async def poll(self, credential: dict, seen_ids: set[str]) -> list[dict]:
        """Poll Gmail once, return new matching messages as event payloads.

        Called by the Temporal activity on each timer tick.
        ``seen_ids`` is maintained by the workflow to avoid re-processing.
        """
        from runtime.gmail_client import get_gmail_service, list_messages, get_message, mark_as_read

        try:
            service = get_gmail_service(credential)
        except Exception as exc:
            logger.error("GmailWatcher: auth failed: %s", exc)
            return []

        query = self._build_query()
        logger.info("GmailWatcher polling: %s", query)

        stubs = list_messages(service, query, max_results=10)
        events: list[dict] = []

        fetch_attachments = self.config.get("fetch_attachments", False)
        filename_filter = self.config.get("filename_filter", "").lower()

        for stub in stubs:
            msg_id = stub["id"]
            if msg_id in seen_ids:
                continue

            msg = get_message(service, msg_id)
            if msg is None:
                continue

            seen_ids.add(msg_id)
            mark_as_read(service, msg_id)

            # Optionally download attachment bytes (base64) for downstream agents
            attachment_payloads: list[dict] = []
            if fetch_attachments and msg.get("attachments"):
                from runtime.gmail_client import get_attachment
                import base64
                for att in msg["attachments"]:
                    # Filter by extension if configured
                    if filename_filter and not att["filename"].lower().endswith(filename_filter):
                        continue
                    raw = get_attachment(service, msg_id, att["attachment_id"])
                    attachment_payloads.append({
                        "filename": att["filename"],
                        "mime_type": att["mime_type"],
                        "data_b64": base64.b64encode(raw).decode("utf-8"),
                    })

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
                    "attachments": attachment_payloads,
                },
            })

        logger.info("GmailWatcher: found %d new messages", len(events))
        return events

    async def run(self, event_name: str, payload: dict) -> dict:
        """Not used directly — agent runs via poll() in the Temporal worker."""
        return {}
