"""Re-export factor matching from ``app.services.rag`` (single implementation)."""

from __future__ import annotations

from pathlib import Path

from app.services.graphrag.neo4j_config import DEFAULT_INVENTORY_PATH
from app.services.rag.factor_matcher import match_checklist_to_factors
from app.services.rag.factor_patterns import load_factor_names as _load_factor_names


def load_factor_names(inventory_path: Path | None = None) -> tuple[str, ...]:
    return _load_factor_names(str(inventory_path or DEFAULT_INVENTORY_PATH))


__all__ = ["load_factor_names", "match_checklist_to_factors"]
