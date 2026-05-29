"""BaseTool — abstract base for all platform tool implementations.

Every tool that a ReactAgent can call must subclass BaseTool and implement:
  - name: str — matches the string in the agent definition's reasoning.tools list
  - description: str — shown to the LLM in the tool list
  - input_schema: dict — JSON Schema for the tool's input parameters
  - execute(input: dict, creds: dict) -> dict — run the tool, return result dict

Credentials come from the agent_tool_configs row for the calling agent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict

    @abstractmethod
    async def execute(self, input: dict, creds: dict) -> dict:
        """Execute the tool and return a result dict."""

    def to_anthropic_spec(self) -> dict:
        """Return the tool spec in Anthropic tool_use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai_spec(self) -> dict:
        """Return the tool spec in OpenAI function-calling format (used by LiteLLM)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
