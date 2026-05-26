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
        credential = self.config.get("_credential", {})

        if not credential:
            return {
                "event": "gmail_sender.email.failed",
                "payload": {"reason": "Gmail credential not configured"},
            }

        # Resolve recipient: payload.to_email > config.forward_to
        forward_to = payload.get("to_email") or self.config.get("forward_to", "")
        if not forward_to:
            return {
                "event": "gmail_sender.email.failed",
                "payload": {"reason": "No recipient: set forward_to in config or provide to_email in payload"},
            }

        # Walk the payload chain to find the original email from GmailWatcher
        # Chain: assignment_generator.payload → pdf_parser.payload → gmail_watcher.payload
        def _find_original_email(p: dict, depth: int = 0) -> dict:
            """Recursively unwrap original_payload until we find an email with thread_id."""
            if p.get("thread_id") and p.get("message_id"):
                return p
            inner = p.get("original_payload")
            if isinstance(inner, dict) and depth < 5:
                return _find_original_email(inner, depth + 1)
            return p

        original_email = _find_original_email(payload)
        reply_to_msg = None
        if original_email.get("thread_id") and original_email.get("message_id"):
            reply_to_msg = {
                "id": original_email["message_id"],
                "thread_id": original_email["thread_id"],
            }

        # If payload carries a pre-composed assignment, send it directly
        if payload.get("assignment_text"):
            fwd_subject = payload.get("subject", "Assignment")
            forward_body = payload["assignment_text"]
        else:
            original = payload.get("original_payload", payload)
            subject = original.get("subject", "(no subject)")
            body = original.get("body", "")
            sender = original.get("sender", "unknown")
            category = payload.get("category", "unknown")
            reasoning = payload.get("reasoning", "")

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
            msg_id = send_message(
                service, forward_to, fwd_subject, forward_body,
                reply_to_msg=reply_to_msg,
            )
            logger.info("Email sent to %s (reply_thread=%s) msg_id=%s",
                        forward_to, reply_to_msg is not None, msg_id)
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
