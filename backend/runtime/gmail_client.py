"""Gmail API client helper.

Builds an authenticated Google API service object from the OAuth credential
blob stored in agent_tool_configs. Handles token refresh automatically.
"""

from __future__ import annotations

import base64
import email as email_lib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import google.auth
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


def _creds_from_blob(credential: dict) -> Credentials:
    """Build a google.oauth2.credentials.Credentials from the stored blob."""
    creds = Credentials(
        token=credential.get("access_token"),
        refresh_token=credential.get("refresh_token"),
        token_uri=credential.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=credential.get("client_id"),
        client_secret=credential.get("client_secret"),
    )
    # Refresh if expired / no access token
    if not creds.valid:
        creds.refresh(Request())
    return creds


def get_gmail_service(credential: dict):
    """Return an authenticated Gmail API service object."""
    creds = _creds_from_blob(credential)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_messages(service, query: str, max_results: int = 20) -> list[dict]:
    """Return a list of message stubs matching *query*."""
    try:
        result = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        return result.get("messages", [])
    except HttpError as e:
        logger.error("Gmail list_messages error: %s", e)
        return []


def get_message(service, msg_id: str) -> dict | None:
    """Fetch the full message and return a simple dict with key fields."""
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
    except HttpError as e:
        logger.error("Gmail get_message error: %s", e)
        return None

    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    body = _extract_body(msg["payload"])
    attachments = _extract_attachments(msg["payload"])

    return {
        "id": msg_id,
        "thread_id": msg.get("threadId", ""),
        "subject": headers.get("subject", ""),
        "sender": headers.get("from", ""),
        "to": headers.get("to", ""),
        "date": headers.get("date", ""),
        "body": body,
        "snippet": msg.get("snippet", ""),
        "label_ids": msg.get("labelIds", []),
        "attachments": attachments,
        "internal_date": int(msg.get("internalDate", 0)),
    }


def _extract_attachments(payload: dict) -> list[dict]:
    """Walk the MIME tree and collect attachment metadata (no bytes yet)."""
    results: list[dict] = []
    _walk_attachments(payload, results)
    return results


def _walk_attachments(part: dict, results: list[dict]) -> None:
    filename = part.get("filename", "")
    body = part.get("body", {})
    attachment_id = body.get("attachmentId")
    if filename and attachment_id:
        results.append({
            "filename": filename,
            "attachment_id": attachment_id,
            "mime_type": part.get("mimeType", "application/octet-stream"),
            "size": body.get("size", 0),
        })
    for sub in part.get("parts", []):
        _walk_attachments(sub, results)


def get_attachment(service, msg_id: str, attachment_id: str) -> bytes:
    """Download and return raw attachment bytes."""
    try:
        result = service.users().messages().attachments().get(
            userId="me", messageId=msg_id, id=attachment_id
        ).execute()
        data = result.get("data", "")
        return base64.urlsafe_b64decode(data + "==")
    except HttpError as e:
        logger.error("Gmail get_attachment error: %s", e)
        return b""


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")

    # Multipart: check parts
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text

    # Fallback: decode whatever body is there
    if body_data:
        return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")

    return ""


def send_message(service, to: str, subject: str, body: str, reply_to_msg: dict | None = None) -> str:
    """Send an email. Returns the sent message id."""
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to_msg:
        msg["In-Reply-To"] = reply_to_msg.get("id", "")
        msg["References"] = reply_to_msg.get("id", "")

    msg.attach(MIMEText(body, "plain"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    kwargs: dict = {"userId": "me", "body": {"raw": raw}}
    if reply_to_msg:
        kwargs["body"]["threadId"] = reply_to_msg.get("thread_id", "")

    result = service.users().messages().send(**kwargs).execute()
    return result["id"]


def mark_as_read(service, msg_id: str) -> None:
    """Remove UNREAD label from a message."""
    try:
        service.users().messages().modify(
            userId="me", id=msg_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
    except HttpError as e:
        logger.warning("Could not mark message as read: %s", e)
