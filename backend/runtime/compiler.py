"""Graph compiler.

Phase 1: validates graph structure (event correctness, filter syntax) and
returns the graph as-is.

Phase 2: will parse nodes/edges, identify trigger nodes, compile them to
Temporal Workflow definitions, and compile downstream nodes to Temporal
Activity chains.
"""

from __future__ import annotations

import ast


def compile_graph(graph_definition: dict) -> dict:
    """Validate and compile a workflow graph definition.

    Parameters
    ----------
    graph_definition:
        React Flow serialised graph: ``{"nodes": [...], "edges": [...]}``.
        Each node carries ``data.agentType``.
        Each edge carries ``data.event`` (event name) and optionally
        ``data.filter`` (Python expression string to evaluate against the
        event payload).

    Returns
    -------
    dict
        ``{"compiled": True, "topology": graph_definition}`` on success.

    Raises
    ------
    ValueError
        If the graph structure is invalid, an edge references an event that
        the source agent does not emit, or a filter expression has a syntax
        error.
    """
    nodes: list[dict] = graph_definition.get("nodes", [])
    edges: list[dict] = graph_definition.get("edges", [])

    if not isinstance(nodes, list):
        raise ValueError("graph_definition.nodes must be a list")
    if not isinstance(edges, list):
        raise ValueError("graph_definition.edges must be a list")

    _validate_edges(nodes, edges)

    return {"compiled": True, "topology": graph_definition}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_edges(nodes: list[dict], edges: list[dict]) -> None:
    """Validate both event names and filter expressions on every edge."""
    from agents import get_agent_class

    node_agent_type: dict[str, str] = {
        node["id"]: node.get("data", {}).get("agentType")
        for node in nodes
        if node.get("data", {}).get("agentType")
    }

    errors: list[str] = []

    for edge in edges:
        edge_id = edge.get("id", "<unknown>")
        edge_data = edge.get("data", {}) or {}
        source_id = edge.get("source", "")
        event_name: str | None = edge_data.get("event")
        filter_expr: str | None = edge_data.get("filter")

        # ── event validation ────────────────────────────────────────────
        if event_name:
            agent_type = node_agent_type.get(source_id)
            if agent_type:
                agent_cls = get_agent_class(agent_type)
                if agent_cls is not None:
                    valid_events = agent_cls.event_names()
                    if event_name not in valid_events:
                        errors.append(
                            f"Edge '{edge_id}': event '{event_name}' is not emitted by "
                            f"'{agent_type}'. Valid events: {valid_events}"
                        )

        # ── filter expression validation ────────────────────────────────
        if filter_expr and filter_expr.strip():
            filter_errors = _validate_filter(filter_expr.strip(), edge_id)
            errors.extend(filter_errors)

    if errors:
        raise ValueError("Graph validation failed:\n" + "\n".join(f"  • {e}" for e in errors))


def _validate_filter(expr: str, edge_id: str) -> list[str]:
    """Check that *expr* is a syntactically valid Python expression.

    Uses :func:`ast.parse` in ``eval`` mode so only expressions (not
    statements) are accepted.  The identifier ``payload`` is expected to
    be in scope at execution time (Phase 2), so referencing it here is fine.

    Examples of valid expressions::

        payload.confidence > 0.8
        payload.category == "pass"
        payload.sender.endswith("@company.com")
        payload.status in ("ok", "approved")

    Returns a list of error strings (empty if valid).
    """
    try:
        ast.parse(expr, mode="eval")
        return []
    except SyntaxError as exc:
        return [
            f"Edge '{edge_id}': filter expression has a syntax error — {exc.msg} "
            f"(line {exc.lineno}, col {exc.offset}). Expression: {expr!r}"
        ]
