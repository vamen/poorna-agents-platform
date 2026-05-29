"""Filesystem tool — read/write files via FileService using FileRef.

The LLM can use this tool to retrieve file contents (e.g. images uploaded
by a Telegram user) or to store data for later use.

No credentials required — uses the platform's FileService.
"""

from __future__ import annotations

import base64
import logging

from tools.base import BaseTool

logger = logging.getLogger(__name__)


class FilesystemTool(BaseTool):
    name = "get_file"
    description = (
        "Retrieve the contents of a file stored by the platform. "
        "Pass the file_ref dict from the message payload. "
        "Returns the file content as a base64-encoded string."
    )
    input_schema = {
        "type": "object",
        "required": ["file_ref"],
        "properties": {
            "file_ref": {
                "type": "object",
                "description": "FileRef dict with file_id, filename, mime_type, backend, uri fields.",
                "properties": {
                    "file_id": {"type": "string"},
                    "filename": {"type": "string"},
                    "mime_type": {"type": "string"},
                    "backend": {"type": "string"},
                    "uri": {"type": "string"},
                },
                "required": ["file_id", "uri", "backend"],
            },
        },
    }

    async def execute(self, input: dict, creds: dict) -> dict:
        from agents.file_ref import FileRef
        from services.file_service import FileService

        ref = FileRef.from_dict(input["file_ref"])
        data = await FileService.get(ref)
        encoded = base64.b64encode(data).decode()
        logger.debug("FilesystemTool: retrieved %s (%d bytes)", ref.filename, len(data))
        return {
            "file_id": ref.file_id,
            "filename": ref.filename,
            "mime_type": ref.mime_type,
            "size_bytes": len(data),
            "content_base64": encoded,
        }


tool = FilesystemTool()
