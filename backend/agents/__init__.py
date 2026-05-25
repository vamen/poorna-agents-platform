"""Agent registry."""

from agents.base import BaseAgent
from agents.gmail_watcher import GmailWatcherAgent
from agents.gmail_sender import GmailSenderAgent
from agents.telegram_gateway import TelegramGatewayAgent
from agents.classifier import ClassifierAgent
from agents.api_caller import ApiCallerAgent

_ALL_AGENTS: list[type[BaseAgent]] = [
    GmailWatcherAgent,
    GmailSenderAgent,
    TelegramGatewayAgent,
    ClassifierAgent,
    ApiCallerAgent,
]

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    cls.agent_type: cls for cls in _ALL_AGENTS
}


def get_agent_class(type_name: str) -> type[BaseAgent] | None:
    return AGENT_REGISTRY.get(type_name)


def instantiate_agent(type_name: str, config: dict) -> BaseAgent:
    cls = get_agent_class(type_name)
    if cls is None:
        raise ValueError(
            f"Unknown agent type: {type_name!r}. "
            f"Registered types: {sorted(AGENT_REGISTRY)}"
        )
    return cls(config)


__all__ = [
    "BaseAgent", "AGENT_REGISTRY", "get_agent_class", "instantiate_agent",
    "GmailWatcherAgent", "GmailSenderAgent", "TelegramGatewayAgent",
    "ClassifierAgent", "ApiCallerAgent",
]
