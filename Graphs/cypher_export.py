"""Render parameterized Cypher as literal statements for Neo4j Browser."""

from __future__ import annotations

from typing import Any


def cypher_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def render_literal_cypher(cypher: str, params: dict[str, Any]) -> str:
    """Replace $param placeholders with escaped literals (Browser-safe)."""
    rendered = cypher
    for key, value in sorted(params.items(), key=lambda item: -len(item[0])):
        rendered = rendered.replace(f"${key}", cypher_literal(value))
    return rendered.strip()
