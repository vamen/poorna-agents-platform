"""API Caller agent — makes a configured HTTP call when triggered.

Events emitted:
  - api.success  {status_code, response}
  - api.failure  {status_code, error}

Phase 2: performs the HTTP request using ``endpoint_url``, ``method``,
``headers``, and ``payload_template`` (with ``{{variable}}`` substitution
from the trigger payload).
"""

from agents.base import BaseAgent


class ApiCallerAgent(BaseAgent):
    """Action agent that fires an HTTP request when triggered."""

    agent_type = "api_caller"

    async def run(self, event_name: str, payload: dict) -> dict:
        """Phase 2: render payload_template, execute HTTP call, return result."""
        return {}
