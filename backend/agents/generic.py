"""GenericAgent — a BaseAgent subclass built dynamically from an AgentDefinition."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from agents.base import BaseAgent
from schemas.agent import TemplateEvent

if TYPE_CHECKING:
    from db.models import AgentDefinition


def make_generic_class(defn: "AgentDefinition") -> type[BaseAgent]:
    """Create a concrete BaseAgent subclass for the given AgentDefinition.

    Reads events and metadata from ``defn.definition`` (the JSON blob).
    A snapshot is taken at class-creation time so the class remains valid
    even if the definition is later updated (the registry re-registers on
    every update).
    """
    d = defn.definition

    # Snapshot events
    snapshot: list[TemplateEvent] = [
        TemplateEvent(name=e["name"], payload=e.get("payload", {}))
        for e in d.get("events", [])
    ]

    _name: str = defn.name
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
            """Phase 1: stub. Phase 2: invoke LLM via reasoning strategy."""
            return {}

        def __repr__(self) -> str:
            return (
                f"GenericAgent(name={_name!r}, "
                f"provider={_primary_provider!r}, model={_primary_model!r}, "
                f"strategy={_strategy!r}, config={self.config!r})"
            )

    _GenericAgent.__name__ = f"GenericAgent_{_name}"
    _GenericAgent.__qualname__ = f"GenericAgent_{_name}"
    return _GenericAgent
