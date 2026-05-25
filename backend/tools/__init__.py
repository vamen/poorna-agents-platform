"""Standard platform toolset.

These are the tools agents can declare in their definition.  In Phase 1 every
tool is a stub that returns mock data.  In Phase 2 each tool executes real
side effects (HTTP calls, Gmail API, etc.).

Usage::

    from tools import STANDARD_TOOLS, get_tool, list_tool_names

    tool = get_tool("http_request")
    tool.name        # "http_request"
    tool.description # "Make an HTTP call …"
    tool.parameters  # {url: …, method: …}
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolParameter:
    type: str                    # string | int | float | bool | object | list
    description: str
    required: bool = False
    default: object | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, ToolParameter] = field(default_factory=dict)
    phase2_only: bool = False    # True → stub in Phase 1, full impl in Phase 2

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                k: {
                    "type": v.type,
                    "description": v.description,
                    "required": v.required,
                    **({"default": v.default} if v.default is not None else {}),
                }
                for k, v in self.parameters.items()
            },
            "phase2_only": self.phase2_only,
        }


STANDARD_TOOLS: dict[str, ToolDefinition] = {
    "http_request": ToolDefinition(
        name="http_request",
        description=(
            "Make an HTTP GET / POST / PUT / DELETE request to any URL. "
            "Returns the response status code and body."
        ),
        parameters={
            "url": ToolParameter(type="string", description="The URL to call", required=True),
            "method": ToolParameter(type="string", description="HTTP method", required=False, default="GET"),
            "headers": ToolParameter(type="object", description="Request headers as key-value pairs", required=False),
            "body": ToolParameter(type="object", description="Request body (for POST/PUT)", required=False),
        },
    ),
    "send_email": ToolDefinition(
        name="send_email",
        description="Send a plain-text email via SMTP.",
        parameters={
            "to": ToolParameter(type="string", description="Recipient email address", required=True),
            "subject": ToolParameter(type="string", description="Email subject line", required=True),
            "body": ToolParameter(type="string", description="Plain-text email body", required=True),
            "from_name": ToolParameter(type="string", description="Sender display name", required=False),
        },
        phase2_only=True,
    ),
    "read_gmail": ToolDefinition(
        name="read_gmail",
        description="Fetch the latest unread emails from a Gmail inbox.",
        parameters={
            "max_results": ToolParameter(type="int", description="Max emails to return", required=False, default=10),
            "label": ToolParameter(type="string", description="Gmail label to filter by", required=False, default="INBOX"),
            "sender_filter": ToolParameter(type="string", description="Only return emails from this sender", required=False),
        },
        phase2_only=True,
    ),
    "send_telegram": ToolDefinition(
        name="send_telegram",
        description="Send a message to a Telegram chat via a configured bot.",
        parameters={
            "chat_id": ToolParameter(type="string", description="Telegram chat or channel ID", required=True),
            "text": ToolParameter(type="string", description="Message text (Markdown supported)", required=True),
        },
        phase2_only=True,
    ),
    "extract_json_field": ToolDefinition(
        name="extract_json_field",
        description=(
            "Extract a nested field from the event payload using dot-notation. "
            "E.g. path='sender.email' on payload {sender: {email: 'x@y.com'}} returns 'x@y.com'."
        ),
        parameters={
            "path": ToolParameter(type="string", description="Dot-separated field path", required=True),
            "default": ToolParameter(type="string", description="Value to return if path is missing", required=False),
        },
    ),
    "render_template": ToolDefinition(
        name="render_template",
        description=(
            "Render a Jinja2 template string using the event payload as context. "
            "Use {{ variable }} syntax."
        ),
        parameters={
            "template": ToolParameter(type="string", description="Jinja2 template string", required=True),
        },
    ),
}


def get_tool(name: str) -> ToolDefinition | None:
    return STANDARD_TOOLS.get(name)


def list_tool_names() -> list[str]:
    return list(STANDARD_TOOLS.keys())
