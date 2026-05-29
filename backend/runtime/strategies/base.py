"""BaseExecutor — abstract base for all reasoning strategy executors."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExecutor(ABC):

    @abstractmethod
    async def run(
        self,
        definition: dict,   # full agent definition blob from AgentDefinition.definition
        config: dict,        # agent instance config (includes _litellm_key, _credential, etc.)
        event_name: str,
        payload: dict,
    ) -> dict:
        """Execute the reasoning strategy and return the output dict.

        Returns a dict with at least:
          {"event": "<emitted_event_name>", "payload": {...}}
        or {} if the agent produces no output.
        """
