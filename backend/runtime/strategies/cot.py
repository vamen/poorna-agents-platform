"""CoTExecutor — Chain-of-Thought: appends step-by-step reasoning suffix."""

from __future__ import annotations

from runtime.strategies.predict import PredictExecutor, _render, _litellm_model_name, _get_client

_COT_SUFFIX = (
    "\n\nThink through this step by step before giving your final answer. "
    "Show your reasoning, then state your conclusion clearly."
)


class CoTExecutor(PredictExecutor):

    async def run(self, definition: dict, config: dict, event_name: str, payload: dict) -> dict:
        reasoning = definition.get("reasoning", {})
        prompt_cfg = reasoning.get("prompt", {})
        models = reasoning.get("model", [])

        system_prompt = prompt_cfg.get("system", "You are a helpful assistant.")
        user_template = prompt_cfg.get("user", "{{ payload }}") + _COT_SUFFIX
        user_content = _render(user_template, event_name, payload)

        client = _get_client(config)
        model_name = _litellm_model_name(models, config)

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
