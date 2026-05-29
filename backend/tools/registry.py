"""Tool registry — maps tool names to BaseTool instances.

Tools are loaded lazily the first time they are requested so import costs
stay proportional to what's actually used.
"""

from __future__ import annotations

import importlib
import logging

from tools.base import BaseTool

logger = logging.getLogger(__name__)

# Map of tool name → module path containing a ``tool`` instance or a Tool class
_TOOL_MODULES: dict[str, str] = {
    "http_request": "tools.http_request.tool",
    "post_to_twitter": "tools.twitter.tool",
    "send_telegram": "tools.telegram_reply.tool",
    "get_file": "tools.filesystem.tool",
    "extract_json_field": "tools.extract_json_field.tool",
    "render_template": "tools.render_template.tool",
}

_cache: dict[str, BaseTool] = {}


def get_tool(name: str) -> BaseTool:
    """Return a shared BaseTool instance for *name*."""
    if name in _cache:
        return _cache[name]

    module_path = _TOOL_MODULES.get(name)
    if not module_path:
        raise KeyError(f"Unknown tool: {name!r}. Available: {list(_TOOL_MODULES)}")

    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(f"Could not import tool module {module_path!r}: {exc}") from exc

    # Expect either a `tool` singleton or a `Tool` class
    if hasattr(mod, "tool"):
        instance = mod.tool
    elif hasattr(mod, "Tool"):
        instance = mod.Tool()
    else:
        raise AttributeError(f"Tool module {module_path!r} must define `tool` or `Tool`")

    _cache[name] = instance
    return instance


def get_tools(names: list[str]) -> list[BaseTool]:
    """Return tool instances for a list of tool names."""
    return [get_tool(n) for n in names]
