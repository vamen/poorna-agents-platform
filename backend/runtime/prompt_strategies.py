"""Prompt strategy builders — CoT and ReAct.

Each strategy is responsible for:
  1. Composing the final system prompt (base + strategy-specific instructions).
  2. Composing the user prompt from the StandardMessage template variables.
  3. For ReAct: injecting tool descriptions into the system prompt.

Usage::

    from runtime.prompt_strategies import build_system_prompt, build_user_prompt

    system = build_system_prompt(
        strategy="react",
        base_system="You are a classifier agent.",
        tools=["http_request", "extract_json_field"],
    )
    user = build_user_prompt(
        template="Event: {{ event_name }}\\nPayload: {{ payload }}",
        vars=message.template_vars(),
    )
"""

from __future__ import annotations

from typing import Literal

Strategy = Literal["cot", "react"]

# ── CoT suffix ────────────────────────────────────────────────────────────────

_COT_SUFFIX = """
---
Think through this step by step before giving your final answer:
1. Understand what the event payload contains and what is being asked.
2. Reason explicitly through each relevant detail.
3. State your conclusion clearly in your final answer.
"""

# ── ReAct suffix (tool use loop) ───────────────────────────────────────────────

_REACT_SUFFIX = """
---
You have access to tools.  Use the following format strictly:

Thought: What do I need to do next?
Action: <tool_name>
Action Input: {{"arg": "value"}}
Observation: <result of the tool call>
... (repeat Thought / Action / Observation as many times as needed)
Thought: I now have enough information to answer.
Final Answer: <your complete answer>

Always end with a "Final Answer:" line.
"""


def _tool_descriptions(tool_names: list[str]) -> str:
    """Build a numbered list of tool descriptions for the ReAct suffix."""
    from tools import get_tool

    lines = ["Available tools:"]
    for name in tool_names:
        tool = get_tool(name)
        if tool is None:
            lines.append(f"  {name}: (unknown tool)")
            continue
        params = ", ".join(
            f"{k} ({'required' if v.required else 'optional'})"
            for k, v in tool.parameters.items()
        )
        lines.append(f"  {name}: {tool.description}")
        if params:
            lines.append(f"    Parameters: {params}")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def build_system_prompt(
    strategy: Strategy,
    base_system: str,
    tools: list[str] | None = None,
) -> str:
    """Return the fully composed system prompt for the given strategy.

    Parameters
    ----------
    strategy:
        ``"cot"`` or ``"react"``.
    base_system:
        The user-defined system prompt template (already rendered with
        ``template_vars``).
    tools:
        List of tool names declared by the agent.  Only relevant for ReAct;
        descriptions are injected into the prompt automatically.
    """
    if strategy == "cot":
        return base_system.rstrip() + "\n" + _COT_SUFFIX

    # ReAct
    tool_block = ""
    if tools:
        tool_block = "\n\n" + _tool_descriptions(tools)

    return base_system.rstrip() + tool_block + "\n" + _REACT_SUFFIX


def build_user_prompt(template: str, vars: dict) -> str:
    """Render the user-prompt template with the given variables.

    Uses simple ``{{ key }}`` substitution (not full Jinja2 for Phase 1).
    Phase 2 can swap this for a proper Jinja2 render.
    """
    result = template
    for key, value in vars.items():
        result = result.replace("{{ " + key + " }}", str(value))
        result = result.replace("{{" + key + "}}", str(value))
    return result


def example_prompts(strategy: Strategy) -> dict[str, str]:
    """Return example system/user prompts for the given strategy.

    Useful for pre-filling the editor with sensible defaults.
    """
    if strategy == "cot":
        return {
            "system": (
                "You are a helpful assistant that analyses incoming events "
                "and produces a structured response."
            ),
            "user": (
                "Event: {{ event_name }}\n\n"
                "Payload:\n{{ payload }}"
            ),
        }
    return {
        "system": (
            "You are an autonomous agent.  Use the tools available to you "
            "to complete the task described in each user message."
        ),
        "user": (
            "Event: {{ event_name }}\n\n"
            "Payload:\n{{ payload }}\n\n"
            "Complete the task using the tools if needed."
        ),
    }
