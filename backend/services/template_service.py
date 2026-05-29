from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

from schemas.agent import TemplateEvent, TemplateResponse

if TYPE_CHECKING:
    from db.models import AgentDefinition

_templates: dict[str, TemplateResponse] = {}

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def load_templates() -> None:
    """Load all predefined YAML templates from disk.

    Files starting with ``_`` are skipped (schema reference docs).
    """
    for yaml_file in TEMPLATES_DIR.glob("*.yaml"):
        if yaml_file.name.startswith("_"):
            continue
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        agent_name = data["name"]
        events = [
            # Keep short names here; agent_cls.event_names() adds the agent_type prefix:
            # "message.received" → event_names() → "telegram_watcher.message.received"
            TemplateEvent(name=e["name"], payload=e.get("payload", {}))
            for e in data.get("events", [])
        ]

        reasoning = data.get("reasoning", {})
        template = TemplateResponse(
            name=agent_name,
            display_name=data["display_name"],
            description=data.get("description", ""),
            is_long_running=data.get("is_long_running", False),
            events=events,
            tools=reasoning.get("tools", []),
            mcp_servers=reasoning.get("mcp_servers", []),
        )
        _templates[template.name] = template


def register_custom_template(defn: "AgentDefinition") -> None:
    """Register (or overwrite) a template entry from an AgentDefinition row.

    The synthetic ``llm_api_key`` tool is prepended to the tools list so that
    AgentConfigPanel always renders an API-key credential form for every custom
    agent instance, regardless of which other tools the definition declares.
    """
    d = defn.definition
    events = [
        TemplateEvent(name=e["name"], payload=e.get("payload", {}))
        for e in d.get("events", [])
    ]
    reasoning = d.get("reasoning", {})
    declared_tools: list[str] = reasoning.get("tools", [])
    # Always surface llm_api_key first so per-instance LLM credentials are
    # configurable even when the definition declares no other tools.
    tools_with_key = ["llm_api_key"] + [t for t in declared_tools if t != "llm_api_key"]
    template = TemplateResponse(
        name=defn.name,
        display_name=d.get("display_name", defn.name),
        description=d.get("description", ""),
        is_long_running=d.get("is_long_running", False),
        events=events,
        tools=tools_with_key,
        mcp_servers=reasoning.get("mcp_servers", []),
    )
    _templates[defn.name] = template


def deregister_custom_template(name: str) -> None:
    _templates.pop(name, None)


def get_all_templates() -> list[TemplateResponse]:
    return list(_templates.values())


def get_template(name: str) -> Optional[TemplateResponse]:
    return _templates.get(name)


def validate_config(agent_type: str, config: dict) -> list[str]:
    """Validate an agent instance's config against its template.

    Custom agents (from AgentDefinition) have no fixed config fields,
    so they always pass here. Predefined templates also no longer declare
    required config fields — validation happens at the service layer.
    """
    template = get_template(agent_type)
    if not template:
        return [f"Unknown agent type: {agent_type}"]
    return []
