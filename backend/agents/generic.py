"""GenericAgent — a BaseAgent subclass built dynamically from an AgentDefinition.

At class-creation time (make_generic_class) the full definition blob is
snapshotted.  At run time, the reasoning strategy is dispatched via
StrategyRegistry so non-engineers can define predict / cot / react agents
entirely from the UI.

Runtime config keys injected by the workflow engine:
  _definition       full AgentDefinition.definition blob
  _litellm_key      per-agent LiteLLM virtual key
  _tool_configs     {tool_name: credential_dict} for react tools
  _credential       primary tool credential (e.g. gmail)
  _gmail_address    for gmail-connected agents
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar

from agents.base import BaseAgent
from schemas.agent import TemplateEvent

if TYPE_CHECKING:
    from db.models import AgentDefinition

logger = logging.getLogger(__name__)


def make_generic_class(defn: "AgentDefinition") -> type[BaseAgent]:
    """Create a concrete BaseAgent subclass for the given AgentDefinition."""
    d = defn.definition

    snapshot: list[TemplateEvent] = [
        TemplateEvent(name=e["name"], payload=e.get("payload", {}))
        for e in d.get("events", [])
    ]

    _name: str = defn.name
    _definition: dict = d
    _strategy: str = d.get("reasoning", {}).get("strategy", "predict")
    _models: list[dict] = d.get("reasoning", {}).get("model", [])
    _primary_provider: str = _models[0]["provider"] if _models else "unknown"
    _primary_model: str = _models[0]["name"] if _models else "unknown"

    class _GenericAgent(BaseAgent):
        agent_type: ClassVar[str] = _name

        @classmethod
        def emitted_events(cls) -> list[TemplateEvent]:
            return snapshot

        @classmethod
        def event_names(cls) -> list[str]:
            return [e.name for e in snapshot]

        async def run(self, event_name: str, payload: dict) -> dict:
            from runtime.strategies import get_executor

            definition = self.config.get("_definition", _definition)
            strategy = definition.get("reasoning", {}).get("strategy", _strategy)

            executor = get_executor(strategy)
            return await executor.run(definition, self.config, event_name, payload)

        def __repr__(self) -> str:
            return (
                f"GenericAgent(name={_name!r}, "
                f"provider={_primary_provider!r}, model={_primary_model!r}, "
                f"strategy={_strategy!r}, config={self.config!r})"
            )

    _GenericAgent.__name__ = f"GenericAgent_{_name}"
    _GenericAgent.__qualname__ = f"GenericAgent_{_name}"
    return _GenericAgent
