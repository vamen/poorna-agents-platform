"""Agent registry."""

from agents.base import BaseAgent
from agents.gmail_watcher import GmailWatcherAgent
from agents.gmail_sender import GmailSenderAgent
from agents.telegram_gateway import TelegramGatewayAgent
from agents.telegram_watcher import TelegramWatcherAgent
from agents.classifier import ClassifierAgent
from agents.api_caller import ApiCallerAgent
from agents.pdf_parser import PdfParserAgent
from agents.assignment_generator import AssignmentGeneratorAgent

_ALL_AGENTS: list[type[BaseAgent]] = [
    GmailWatcherAgent,
    GmailSenderAgent,
    TelegramGatewayAgent,
    TelegramWatcherAgent,
    ClassifierAgent,
    ApiCallerAgent,
    PdfParserAgent,
    AssignmentGeneratorAgent,
]

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    cls.agent_type: cls for cls in _ALL_AGENTS
}


def get_agent_class(type_name: str) -> type[BaseAgent] | None:
    return AGENT_REGISTRY.get(type_name)


def instantiate_agent(type_name: str, config: dict) -> BaseAgent:
    cls = get_agent_class(type_name)
    if cls is None:
        # Fall back to GenericAgent when _definition is injected by the
        # workflow engine (custom agents defined via AgentDefinition).
        definition = config.get("_definition")
        if definition:
            from agents.generic import make_generic_class
            from types import SimpleNamespace

            cls = make_generic_class(SimpleNamespace(name=type_name, definition=definition))
        else:
            raise ValueError(
                f"Unknown agent type: {type_name!r}. "
                f"Registered types: {sorted(AGENT_REGISTRY)}"
            )
    return cls(config)


__all__ = [
    "BaseAgent", "AGENT_REGISTRY", "get_agent_class", "instantiate_agent",
    "GmailWatcherAgent", "GmailSenderAgent", "TelegramGatewayAgent", "TelegramWatcherAgent",
    "ClassifierAgent", "ApiCallerAgent", "PdfParserAgent", "AssignmentGeneratorAgent",
]
