"""Map encoder checklist items to red-flag graph Factor names (regex-first)."""

from __future__ import annotations

from pathlib import Path

from app.schemas import ChecklistItem
from app.services.graphrag.neo4j_config import DEFAULT_INVENTORY_PATH
from app.services.graphrag.schemas import FactorMatch
from app.services.rag.factor_patterns import (
    _age_implies_over_50,
    _norm,
    _sex_factor,
    build_factor_patterns,
    load_factor_names,
)


def _match_item_to_factor(
    item: ChecklistItem,
    factors: tuple[str, ...],
    patterns: tuple,
) -> FactorMatch:
    text = (item.text or "").strip()
    dumped = item.model_dump()
    if not text:
        return FactorMatch(checklist_item=dumped, match_method="empty", match_score=0.0)

    low = _norm(text)
    factor_set = set(factors)

    if item.kind == "demographic" and item.label == "age" and _age_implies_over_50(text):
        if "Age over 50" in factor_set:
            return FactorMatch(
                checklist_item=dumped,
                factor_name="Age over 50",
                match_method="checklist_kind",
                match_score=1.0,
            )

    if item.kind == "demographic" and item.label == "sex":
        sex_factor = _sex_factor(text)
        if sex_factor and sex_factor in factor_set:
            return FactorMatch(
                checklist_item=dumped,
                factor_name=sex_factor,
                match_method="checklist_kind",
                match_score=1.0,
            )

    best: FactorMatch | None = None
    for fp in patterns:
        if fp.checklist_kinds and item.kind not in fp.checklist_kinds:
            continue
        if fp.checklist_labels and item.label not in fp.checklist_labels:
            continue
        if fp.checklist_kinds and fp.checklist_labels and fp.factor_name in factor_set:
            if item.kind == "demographic" and item.label == "sex":
                continue
            return FactorMatch(
                checklist_item=dumped,
                factor_name=fp.factor_name,
                match_method="checklist_kind",
                match_score=0.95,
            )

        for pat in fp.patterns:
            if pat.search(text) or pat.search(low):
                score = 0.98 if fp.priority >= 10 else 0.9
                method = "regex" if fp.priority < 10 else "checklist_kind"
                candidate = FactorMatch(
                    checklist_item=dumped,
                    factor_name=fp.factor_name,
                    match_method=method,
                    match_score=score,
                )
                if best is None or candidate.match_score > best.match_score:
                    best = candidate

    if best and best.factor_name:
        return best

    best_name: str | None = None
    best_score = 0.0
    text_tokens = set(low.split())
    for factor in factors:
        factor_low = _norm(factor)
        if low == factor_low:
            return FactorMatch(
                checklist_item=dumped,
                factor_name=factor,
                match_method="factor_name_exact",
                match_score=1.0,
            )
        if item.kind == "demographic" and item.label == "sex":
            continue
        factor_tokens = set(factor_low.split())
        if not factor_tokens:
            continue
        overlap = len(text_tokens & factor_tokens) / len(factor_tokens)
        score = overlap * 0.75
        if score > best_score:
            best_score = score
            best_name = factor

    if best_name and best_score >= 0.75:
        return FactorMatch(
            checklist_item=dumped,
            factor_name=best_name,
            match_method="fuzzy_fallback",
            match_score=best_score,
        )

    return FactorMatch(
        checklist_item=dumped,
        factor_name=None,
        match_method="none",
        match_score=best_score,
    )


def match_checklist_to_factors(
    items: list[ChecklistItem] | list[dict[str, str]],
    *,
    inventory_path: Path | None = None,
) -> list[FactorMatch]:
    """Resolve checklist rows to graph Factor names (deduped by factor)."""
    inv = str(inventory_path or DEFAULT_INVENTORY_PATH)
    factors = load_factor_names(inv)
    patterns = build_factor_patterns(inv)
    parsed: list[ChecklistItem] = []
    for row in items:
        if isinstance(row, ChecklistItem):
            parsed.append(row)
        else:
            parsed.append(ChecklistItem.model_validate(row))

    seen_factors: set[str] = set()
    matches: list[FactorMatch] = []
    for item in parsed:
        match = _match_item_to_factor(item, factors, patterns)
        if match.factor_name and match.factor_name in seen_factors:
            continue
        if match.factor_name:
            seen_factors.add(match.factor_name)
        matches.append(match)
    return matches
