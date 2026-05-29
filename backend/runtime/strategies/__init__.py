"""Strategy registry — maps reasoning strategy names to executor classes.

Usage::

    from runtime.strategies import get_executor
    executor = get_executor("react")
    result = await executor.run(definition, config, event_name, payload)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.strategies.base import BaseExecutor

_REGISTRY: dict[str, str] = {
    "predict": "runtime.strategies.predict.PredictExecutor",
    "cot": "runtime.strategies.cot.CoTExecutor",
    "react": "runtime.strategies.react.ReactExecutor",
}


def get_executor(strategy: str) -> "BaseExecutor":
    """Return an executor instance for *strategy*."""
    import importlib

    dotpath = _REGISTRY.get(strategy)
    if not dotpath:
        raise KeyError(f"Unknown strategy: {strategy!r}. Available: {list(_REGISTRY)}")

    module_path, class_name = dotpath.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()
