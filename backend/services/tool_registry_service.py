"""Tool & MCP server template registry.

Loads per-tool YAML templates from ``tools/<name>/`` at startup.

Three files per tool:
  meta.yaml   — name, display_name, kind (tool|mcp_server), phase, icon
  schema.yaml — pure JSON Schema for credential/config validation
  ui.yaml     — rendering hints for the frontend form renderer

Usage::

    from services.tool_registry_service import tool_registry

    # list all available tools
    all_meta = tool_registry.list_tools()

    # get a specific tool
    entry = tool_registry.get("gmail")
    entry.meta     # dict
    entry.schema   # dict  (JSON Schema)
    entry.ui       # dict

    # validate a config blob against the schema
    tool_registry.validate_config("gmail", {"gmail_address": "x@gmail.com", ...})
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ── Tool entry ───────────────────────────────────────────────────────────────

TOOLS_DIR = Path(__file__).parent.parent / "tools"


@dataclass
class ToolEntry:
    meta: dict
    schema: dict
    ui: dict

    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def kind(self) -> str:
        return self.meta.get("kind", "tool")

    @property
    def phase(self) -> int:
        return self.meta.get("phase", 1)


# ── Registry ─────────────────────────────────────────────────────────────────

class ToolRegistry:
    """In-memory registry of all loaded tool templates."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def load(self) -> None:
        """Scan ``tools/`` and load every subdirectory that has a meta.yaml."""
        loaded: list[str] = []
        errors: list[str] = []

        if not TOOLS_DIR.exists():
            logger.warning("tools/ directory not found at %s — skipping tool registry load", TOOLS_DIR)
            return

        for tool_dir in sorted(TOOLS_DIR.iterdir()):
            if not tool_dir.is_dir():
                continue
            meta_path = tool_dir / "meta.yaml"
            if not meta_path.exists():
                continue  # not a tool directory

            try:
                meta = yaml.safe_load(meta_path.read_text())
                schema_path = tool_dir / "schema.yaml"
                schema = yaml.safe_load(schema_path.read_text()) if schema_path.exists() else {}
                ui_path = tool_dir / "ui.yaml"
                ui = yaml.safe_load(ui_path.read_text()) if ui_path.exists() else {}

                entry = ToolEntry(meta=meta, schema=schema, ui=ui)
                self._tools[entry.name] = entry
                loaded.append(entry.name)
            except Exception as exc:
                errors.append(f"{tool_dir.name}: {exc}")

        if loaded:
            logger.info("Tool registry loaded: %s", ", ".join(loaded))
        if errors:
            logger.error("Tool registry errors: %s", "; ".join(errors))

    # ── Read API ──────────────────────────────────────────────────────────────

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """Return all meta dicts, sorted by name."""
        return [e.meta for e in sorted(self._tools.values(), key=lambda e: e.name)]

    def list_by_kind(self, kind: str) -> list[dict]:
        """Return meta dicts for tools matching a given kind (tool | mcp_server)."""
        return [e.meta for e in self._tools.values() if e.kind == kind]

    def get_schema(self, name: str) -> dict | None:
        entry = self._tools.get(name)
        return entry.schema if entry else None

    def get_ui(self, name: str) -> dict | None:
        entry = self._tools.get(name)
        return entry.ui if entry else None

    def validate_config(self, name: str, config: dict) -> list[str]:
        """Validate *config* against the tool's JSON Schema.

        Returns a list of error strings. Empty list means valid.
        Uses ``jsonschema`` if installed; falls back to a no-op validator.
        """
        entry = self._tools.get(name)
        if not entry or not entry.schema:
            return []

        try:
            import jsonschema  # optional dep
            validator = jsonschema.Draft202012Validator(entry.schema)
            errors = sorted(validator.iter_errors(config), key=lambda e: list(e.absolute_path))
            return [e.message for e in errors]
        except ImportError:
            # jsonschema not installed — skip validation
            return []
        except Exception as exc:
            return [str(exc)]


# ── Singleton ─────────────────────────────────────────────────────────────────

tool_registry = ToolRegistry()
