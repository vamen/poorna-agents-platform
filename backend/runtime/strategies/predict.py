"""PredictExecutor — bare LLM call, no scaffolding (mirrors DSPy Predict)."""

from __future__ import annotations

import json
import logging

from runtime.strategies.base import BaseExecutor

logger = logging.getLogger(__name__)


class PredictExecutor(BaseExecutor):

    async def run(self, definition: dict, config: dict, event_name: str, payload: dict) -> dict:
        reasoning = definition.get("reasoning", {})
        prompt_cfg = reasoning.get("prompt", {})
        models = reasoning.get("model", [])

        system_prompt = prompt_cfg.get("system", "You are a helpful assistant.")
        user_template = prompt_cfg.get("user", "{{ payload }}")

        user_content = _render(user_template, event_name, payload)

        provider = models[0].get("provider", "anthropic") if models else "anthropic"
        client = _get_client(config, provider=provider)
        model_name = _litellm_model_name(models, config, provider=provider)

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )

        text = response.choices[0].message.content or ""
        events = definition.get("events", [])
        first_event = events[0]["name"] if events else "result"

        return {"event": f"{definition['name']}.{first_event}", "payload": {"result": text}}


def _render(template: str, event_name: str, payload: dict) -> str:
    """Render a Jinja2 template with event_name and payload as context.

    Supports:
    - ``{{ event_name }}``
    - ``{{ payload }}``             → full JSON dump
    - ``{{ payload.field }}``       → payload["field"]
    - ``{{ payload.field | default('…') }}`` and all standard Jinja2 filters
    """
    from jinja2 import Environment, Undefined

    env = Environment(undefined=Undefined)

    class _PayloadProxy:
        """Wraps a dict so ``payload.key`` works in Jinja2 templates."""
        def __init__(self, data: dict):
            self._data = data

        def __getattr__(self, name: str):
            val = self._data.get(name, "")
            # Render empty lists/dicts as empty string so templates stay clean
            if isinstance(val, (list, dict)) and not val:
                return ""
            return val

        def __str__(self):
            return json.dumps(self._data, indent=2)

        def __repr__(self):
            return self.__str__()

    try:
        tmpl = env.from_string(template)
        return tmpl.render(event_name=event_name, payload=_PayloadProxy(payload))
    except Exception:
        # Fallback to old behaviour if template is somehow broken
        return (
            template
            .replace("{{ event_name }}", event_name)
            .replace("{{ payload }}", json.dumps(payload, indent=2))
        )


_PROVIDER_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1",
    "openai": "https://api.openai.com/v1",
}


def _litellm_model_name(models: list[dict], config: dict, provider: str = "anthropic") -> str:
    """Return the plain model name to pass to the provider API."""
    if not models:
        return "claude-sonnet-4-6"
    m = models[0]
    return m.get("name", "claude-sonnet-4-6")


def _get_client(config: dict, provider: str = "anthropic"):
    """Return an OpenAI-compatible client routed directly to the provider.

    Priority:
    1. ``_api_key`` in config  →  user's own key, hit provider directly
    2. Platform ``settings.anthropic_api_key``  →  fall back to platform key
    """
    from openai import OpenAI

    api_key = config.get("_api_key")
    if api_key:
        base_url = _PROVIDER_BASE_URLS.get(provider, _PROVIDER_BASE_URLS["anthropic"])
        return OpenAI(api_key=api_key, base_url=base_url)

    # No user key — use platform key (Anthropic default)
    from config import settings
    return OpenAI(api_key=settings.anthropic_api_key, base_url=_PROVIDER_BASE_URLS["anthropic"])
