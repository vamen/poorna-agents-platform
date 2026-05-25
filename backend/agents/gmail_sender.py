"""GmailSender agent — sends/forwards an email via Gmail API.

Events emitted:
    email.sent    {to, subject, message_id}
    email.failed  {reason}

Agent config (from canvas):
    forward_to   — recipient address, e.g. "vivekstarstar@gmail.com"

Tool config (from agent_tool_configs, stored after OAuth):
    gmail_address  — authenticated sender address
    credential     — OAuth2 credential blob
"""

from __future__ import annotations

import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class GmailSenderAgent(BaseAgent):
    agent_type = "gmail_sender"

    async def run(self, event_name: str, payload: dict) -> dict:
        """Send an email using the Gmail API.

        ``payload`` is expected to contain the original email data
        (from the classifier's ``original_payload`` field) plus
        classification details.
        """
        forward_to = self.config.get("forward_to", "")
        credential = self.config.get("_credential", {})

        if not forward_to:
            return {
                "event": "gmail_sender.email.failed",
                "payload": {"reason": "forward_to not configured"},
            }
        if not credential:
            return {
                "event": "gmail_sender.email.failed",
                "payload": {"reason": "Gmail credential not configured"},
            }

        original = payload.get("original_payload", payload)
        subject = original.get("subject", "(no subject)")
        body = original.get("body", "")
        sender = original.get("sender", "unknown")
        category = payload.get("category", "unknown")
        reasoning = payload.get("reasoning", "")

        # Build forwarded body
        forward_body = (
            f"[Forwarded by Agent Platform — classified as '{category}']\n"
            f"Reasoning: {reasoning}\n\n"
            f"--- Original email ---\n"
            f"From: {sender}\n"
            f"Subject: {subject}\n\n"
            f"{body}"
        )

        fwd_subject = f"Fwd: {subject}"

        from runtime.gmail_client import get_gmail_service, send_message
        try:
            service = get_gmail_service(credential)
            msg_id = send_message(service, forward_to, fwd_subject, forward_body)
            logger.info("Email forwarded to %s, msg_id=%s", forward_to, msg_id)
        except Exception as exc:
            logger.error("GmailSender send failed: %s", exc)
            return {
                "event": "gmail_sender.email.failed",
                "payload": {"reason": str(exc)},
            }

        return {
            "event": "gmail_sender.email.sent",
            "payload": {
                "to": forward_to,
                "subject": fwd_subject,
                "message_id": msg_id,
            },
        }
