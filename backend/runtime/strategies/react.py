"""ReactExecutor — drives a synchronous Claude tool_use (ReAct) loop.

Algorithm
---------
1. Read definition.reasoning.{tools, prompt, model, max_iterations}.
2. Load BaseTool instances from the tool registry.
3. Gather per-tool credentials from config["_tool_configs"][tool_name].
4. Run the Claude tool_use loop:
   a. Send messages + tool specs to the LLM.
   b. If response contains tool_use blocks, execute each tool and append
      tool_result blocks.
   c. Repeat until the model emits a text-only response or max_iterations
      is reached.
5. Parse the final text to determine which event to emit.
   - The LLM is instructed to end with a JSON fence: ```json\n{"event": "...", "payload": {...}}\n```
   - Fallback: use the first defined event with the raw text as result.
"""

from __future__ import annotations

import json
import logging
import re

from runtime.strategies.base import BaseExecutor
from runtime.strategies.predict import _render, _litellm_model_name, _get_client

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


class ReactExecutor(BaseExecutor):

    async def run(self, definition: dict, config: dict, event_name: str, payload: dict) -> dict:
        reasoning = definition.get("reasoning", {})
        prompt_cfg = reasoning.get("prompt", {})
        models = reasoning.get("model", [])
        tool_names: list[str] = reasoning.get("tools", [])
        max_iterations: int = reasoning.get("max_iterations", 10)

        system_prompt = _build_system(prompt_cfg, definition)
        user_content = _render(prompt_cfg.get("user", "{{ payload }}"), event_name, payload)

        # Prepend conversation history if requested
        context_n: int = reasoning.get("context_messages", 0)
        history_messages: list[dict] = []
        if context_n > 0:
            session_id: str = config.get("_session_id", "")
            agent_id: str = config.get("_agent_id", "")
            # Use chat_id from payload as conversation thread key so history
            # spans across multiple Telegram messages (each a separate session)
            chat_id: str = str(payload.get("chat_id", ""))
            if session_id:
                history_messages = await _load_session_history(
                    session_id, agent_id, context_n, chat_id=chat_id
                )

        # Load tools
        from tools.registry import get_tools
        tools = get_tools(tool_names)
        tool_specs = [t.to_anthropic_spec() for t in tools]
        tool_map = {t.name: t for t in tools}

        # Per-tool credential blobs
        tool_configs: dict[str, dict] = config.get("_tool_configs", {})

        provider = models[0].get("provider", "anthropic") if models else "anthropic"
        client = _get_client(config, provider=provider)
        model_name = _litellm_model_name(models, config, provider=provider)

        # OpenAI-compatible message format: system as first message
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            *history_messages,
            {"role": "user", "content": user_content},
        ]

        # OpenAI-compatible tool specs
        tool_specs_openai = [t.to_openai_spec() for t in tools]

        for iteration in range(max_iterations):
            kwargs: dict = {
                "model": model_name,
                "messages": messages,
                "max_tokens": 4096,
            }
            if tool_specs_openai:
                kwargs["tools"] = tool_specs_openai
                # Force a tool call on the first iteration — the agent has no other
                # channel to reach the user, so a text-only response on iteration 0
                # is always a mistake.
                if iteration == 0:
                    kwargs["tool_choice"] = "required"

            response = client.chat.completions.create(**kwargs)
            msg = response.choices[0].message

            # Collect tool calls from the response
            tool_calls = msg.tool_calls or []

            logger.debug(
                "ReactExecutor[%s] iter %d: finish_reason=%s tool_calls=%d content_len=%d",
                definition["name"], iteration + 1,
                response.choices[0].finish_reason,
                len(tool_calls),
                len(msg.content or ""),
            )
            if tool_calls:
                logger.info(
                    "ReactExecutor[%s] iter %d: calling tools %s",
                    definition["name"], iteration + 1,
                    [tc.function.name for tc in tool_calls],
                )
            else:
                logger.info(
                    "ReactExecutor[%s] iter %d: no tool calls — finish_reason=%s — content=%r",
                    definition["name"], iteration + 1,
                    response.choices[0].finish_reason,
                    (msg.content or "")[:300],
                )

            if not tool_calls:
                # Final answer — no more tool calls
                final_text = msg.content or ""
                logger.info(
                    "ReactExecutor[%s]: done after %d iteration(s)",
                    definition["name"], iteration + 1,
                )
                return _parse_final(final_text, definition)

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            # Execute each tool and append results in OpenAI format (role=tool)
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                tool_instance = tool_map.get(tool_name)
                if not tool_instance:
                    result_content = json.dumps({"error": f"Tool {tool_name!r} not found"})
                else:
                    # Inject session context into creds so tools can persist messages
                    creds = {
                        **tool_configs.get(tool_name, {}),
                        "_session_id": config.get("_session_id", ""),
                        "_agent_id": config.get("_agent_id", ""),
                    }
                    try:
                        result = await tool_instance.execute(tool_input, creds)
                        result_content = json.dumps(result)
                    except Exception as exc:
                        logger.error("Tool %s failed: %s", tool_name, exc)
                        result_content = json.dumps({"error": str(exc)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_content,
                })

        # Max iterations reached — ask for final answer without tools
        logger.warning(
            "ReactExecutor[%s]: max_iterations=%d reached, forcing final answer",
            definition["name"], max_iterations,
        )
        response = client.chat.completions.create(
            model=model_name,
            messages=messages + [{"role": "user", "content": "Provide your final answer now."}],
            max_tokens=2048,
        )
        final_text = response.choices[0].message.content or ""
        return _parse_final(final_text, definition)


async def _load_session_history(
    session_id: str, agent_id: str, n: int, chat_id: str = ""
) -> list[dict]:
    """Build conversation history for the react agent.

    When ``chat_id`` is provided (Telegram chat), we query across ALL sessions
    by matching ``payload->chat_id`` — this stitches together what is otherwise
    a new session per Telegram message into one continuous conversation thread.

    Without ``chat_id`` we fall back to messages in the current session only.

    Role assignment:
    - Sender ref_id == agent_id  → ``role: assistant``  (agent spoke to user)
    - Anything else               → ``role: user``       (user spoke to agent)
    """
    import sqlalchemy as sa
    from sqlalchemy.orm import joinedload
    from db.base import AsyncSessionLocal
    from db.models import AgentMessage

    async with AsyncSessionLocal() as db:
        if chat_id:
            # Cross-session lookup: all messages whose payload contains this chat_id.
            # Works for both inbound (telegram_watcher saves chat_id in payload)
            # and outbound (send_telegram saves chat_id in payload).
            result = await db.execute(
                sa.select(AgentMessage)
                .options(joinedload(AgentMessage.sender), joinedload(AgentMessage.recipient))
                .where(
                    sa.func.json_extract(AgentMessage.payload, "$.chat_id") == chat_id
                )
                .order_by(AgentMessage.created_at.desc())
                .limit(n)
            )
        else:
            result = await db.execute(
                sa.select(AgentMessage)
                .options(joinedload(AgentMessage.sender), joinedload(AgentMessage.recipient))
                .where(AgentMessage.session_id == session_id)
                .order_by(AgentMessage.created_at.desc())
                .limit(n)
            )
        rows = result.scalars().all()

    history: list[dict] = []
    for row in reversed(rows):
        p = row.payload or {}
        text = p.get("text") or p.get("result") or ""
        if not text:
            continue
        sender = row.sender
        role = "assistant" if (sender and sender.ref_id == agent_id) else "user"
        history.append({"role": role, "content": str(text)})
    return history


def _build_system(prompt_cfg: dict, definition: dict) -> str:
    base = prompt_cfg.get("system", "You are a helpful assistant.")
    events = definition.get("events", [])
    event_names = [f"{definition['name']}.{e['name']}" for e in events]
    suffix = (
        "\n\n---\n"
        "CRITICAL RULES:\n"
        "1. You are NOT in a direct chat with the user. Any text you write is INVISIBLE "
        "to the user — they will NEVER see it. The ONLY way to communicate with the user "
        "is by calling a tool (e.g. send_telegram). Always call a tool to talk to the user.\n"
        "2. When your task is fully complete (all tool work done), end by outputting ONLY "
        "a JSON block — no other text:\n"
        "```json\n"
        '{"event": "<event_name>", "payload": {...}}\n'
        "```\n"
        f"Available event names: {event_names}"
    )
    return base + suffix


def _parse_final(text: str, definition: dict) -> dict:
    """Extract the event/payload JSON block from the LLM's final response."""
    match = _JSON_FENCE.search(text)
    if match:
        try:
            data = json.loads(match.group(1))
            if "event" in data:
                return data
        except json.JSONDecodeError:
            pass

    # Fallback: use first defined event, put raw text as result
    events = definition.get("events", [])
    first_event = f"{definition['name']}.{events[0]['name']}" if events else f"{definition['name']}.result"
    return {"event": first_event, "payload": {"result": text}}
