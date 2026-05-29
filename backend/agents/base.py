"""Base class for all agent types in the platform.

Every concrete agent must:
  1. Set the ``agent_type`` ClassVar to match its YAML template filename
     (without the .yaml extension).
  2. Optionally override ``run()`` for Phase 2 execution logic.

The key contract is ``emitted_events()`` — a classmethod that returns the
full event schemas this agent type can emit, sourced from the YAML template
that is loaded and cached at application startup.  This means:

  - You can call it before any agent instance exists (useful in graph validation
    and workflow compilation).
  - It is always in sync with the YAML definition — no duplication.

Usage::

    from agents import get_agent_class

    cls = get_agent_class("gmail_watcher")
    cls.event_names()          # ["gmail_watcher.email.received", "gmail_watcher.email.error"]
    cls.emitted_events()       # [TemplateEvent(name="email.received", ...), ...]

    agent = cls(config={"label_filter": "INBOX"})
    await agent.run("email.received", payload)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from schemas.agent import TemplateEvent


class BaseAgent(ABC):
    """Abstract base for every agent type.

    Class attributes
    ----------------
    agent_type : str
        Must be set by every subclass.  Must exactly match the ``type`` field
        in the corresponding YAML template file.
    """

    agent_type: ClassVar[str]

    def __init__(self, config: dict) -> None:
        """
        Parameters
        ----------
        config:
            The user-supplied configuration values for this agent instance,
            validated against the template's ``fields`` schema.
        """
        self.config: dict = config

    # ------------------------------------------------------------------
    # Event contract
    # ------------------------------------------------------------------

    @classmethod
    def emitted_events(cls) -> list["TemplateEvent"]:
        """Return the full event schemas this agent type can emit.

        Reads from the in-memory template cache populated at startup by
        ``services.template_service.load_templates()``.  Returns an empty
        list if the template has not been loaded yet (e.g. in tests that
        skip startup).

        Returns
        -------
        list[TemplateEvent]
            Each entry has ``.name`` (str) and ``.payload_schema`` (dict).
        """
        from services.template_service import get_template

        template = get_template(cls.agent_type)
        if template is None:
            return []
        return list(template.events)

    @classmethod
    def event_names(cls) -> list[str]:
        """Return the namespaced event name strings this agent type can emit.

        Each event name is prefixed with ``agent_type`` to prevent collisions
        when multiple agent types share similar event names (e.g. both
        ``gmail_watcher`` and ``gmail_sender`` deal with email events).

        Convention: ``<agent_type>.<short_event_name>``

        Convenience wrapper around :meth:`emitted_events`.

        Returns
        -------
        list[str]
            E.g. ``["gmail_watcher.email.received", "gmail_watcher.email.error"]``
        """
        return [f"{cls.agent_type}.{e.name}" for e in cls.emitted_events()]

    # ------------------------------------------------------------------
    # LLM client factory
    # ------------------------------------------------------------------

    def _get_llm_client(self):
        """Return an OpenAI-compatible client routed through LiteLLM proxy.

        Uses the workflow's virtual key when available; falls back to direct
        Anthropic API so agents work even before LiteLLM is running.
        """
        from openai import OpenAI

        litellm_key = self.config.get("_litellm_key")
        if litellm_key:
            from config import settings
            return OpenAI(
                api_key=litellm_key,
                base_url=settings.litellm_base_url,
            )

        from config import settings
        return OpenAI(
            api_key=settings.anthropic_api_key,
            base_url="https://api.anthropic.com/v1",
        )

    # ------------------------------------------------------------------
    # Execution stub (Phase 2)
    # ------------------------------------------------------------------

    async def run(self, event_name: str, payload: dict) -> dict:
        """Execute agent logic for an incoming event and return an output payload.

        Parameters
        ----------
        event_name:
            The triggering event, e.g. ``"email.received"``.
        payload:
            The data accompanying the event.

        Returns
        -------
        dict
            Phase 1: always ``{}``.
            Phase 2: the agent's output payload, whose structure matches one
            of the entries in :meth:`emitted_events`.
        """
        return {}

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self.agent_type!r}, config={self.config!r})"
