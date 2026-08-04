"""Map encoder checklist items to red-flag graph Factor names (regex-first).

When ``DIGIMSK_LLM_FACTOR_MATCH=1``, unmatched (non-gated) rows get one batched
LLM cross-check against the inventory Factor list before GraphRAG traversal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.schemas import ChecklistItem
from app.services.graphrag.neo4j_config import DEFAULT_INVENTORY_PATH
from app.services.graphrag.schemas import FactorMatch
from app.services.rag.factor_patterns import (
    _age_implies_over_50,
    _norm,
    _severity_implies_severe,
    _sex_factor,
    build_factor_patterns,
    load_factor_names,
)
from app.services.rag.llm_factor_match import llm_match_unmatched_factors


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

    if item.kind == "demographic" and item.label == "age":
        if _age_implies_over_50(text) and "Age over 50" in factor_set:
            return FactorMatch(
                checklist_item=dumped,
                factor_name="Age over 50",
                match_method="checklist_kind",
                match_score=1.0,
            )
        # Under-50 (or non-numeric) age rows must not match via other shortcuts.
        return FactorMatch(
            checklist_item=dumped,
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )

    if item.kind == "severity" and item.label == "symptom_severity":
        if _severity_implies_severe(text) and "Severe pain" in factor_set:
            return FactorMatch(
                checklist_item=dumped,
                factor_name="Severe pain",
                match_method="checklist_kind",
                match_score=1.0,
            )
        return FactorMatch(
            checklist_item=dumped,
            factor_name=None,
            match_method="none",
            match_score=0.0,
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
            # Sex / age / severity handled above with text predicates.
            if item.kind == "demographic" and item.label in ("sex", "age"):
                continue
            if item.kind == "severity" and item.label == "symptom_severity":
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


def _gap_for_match(match: FactorMatch) -> dict[str, str] | None:
    """Classify coverage gaps / suspect matches for session audit."""
    item = match.checklist_item or {}
    kind = str(item.get("kind") or "")
    label = str(item.get("label") or "")
    text = str(item.get("text") or "").strip()

    if match.match_method == "empty":
        return {
            "code": "empty_text",
            "detail": "Checklist item has empty text; no Factor can be matched.",
        }
    if kind == "severity" and label == "symptom_severity" and not match.factor_name:
        return {
            "code": "severity_below_threshold",
            "detail": (
                f"Severity {text!r} did not meet severe criteria "
                "(numeric ≥7 or severe-class words)."
            ),
        }
    if kind == "demographic" and label == "age" and not match.factor_name:
        return {
            "code": "age_below_threshold",
            "detail": f"Age {text!r} did not imply ≥50; Age over 50 not applied.",
        }
    if kind == "demographic" and label == "sex" and not match.factor_name:
        return {
            "code": "sex_unresolved",
            "detail": f"Sex text {text!r} did not map to Male sex / Female sex.",
        }
    if match.match_method == "fuzzy_fallback" and match.factor_name:
        return {
            "code": "fuzzy_match",
            "detail": (
                f"Low-confidence fuzzy attach of {text!r} → {match.factor_name!r} "
                f"(score={match.match_score:.2f}); review for false positive."
            ),
        }
    if (
        match.factor_name == "Constant pain"
        and kind == "palliative"
        and label == "rest"
        and match.match_method == "checklist_kind"
    ):
        return {
            "code": "suspect_blind_kind_map",
            "detail": (
                "palliative/rest mapped to Constant pain via kind/label only; "
                "rest relief is clinically inverted vs constant pain."
            ),
        }
    if not match.factor_name:
        return {
            "code": "unmatched",
            "detail": (
                f"No graph Factor matched for {text!r} "
                f"(kind={kind!r}, label={label!r})."
            ),
        }
    return None


def build_factor_matching_audit(
    matches: list[FactorMatch],
) -> dict[str, Any]:
    """Serialize per-item factor matching decisions for session / UI logging."""
    items: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    methods: dict[str, int] = {}
    matched_names: list[str] = []
    seen_factors: set[str] = set()

    for match in matches:
        gap = _gap_for_match(match)
        status = "matched" if match.factor_name else "unmatched"
        if gap and gap["code"] in {
            "severity_below_threshold",
            "age_below_threshold",
            "sex_unresolved",
        }:
            status = "gated"
        entry: dict[str, Any] = {
            "checklist_item": dict(match.checklist_item or {}),
            "factor_name": match.factor_name,
            "match_method": match.match_method,
            "match_score": round(float(match.match_score), 4),
            "status": status,
            "gap": gap,
        }
        items.append(entry)
        methods[match.match_method] = methods.get(match.match_method, 0) + 1
        if match.factor_name and match.factor_name not in seen_factors:
            seen_factors.add(match.factor_name)
            matched_names.append(match.factor_name)
        if gap:
            gaps.append(
                {
                    "code": gap["code"],
                    "detail": gap["detail"],
                    "checklist_item": entry["checklist_item"],
                    "factor_name": match.factor_name,
                    "match_method": match.match_method,
                    "match_score": entry["match_score"],
                }
            )

    unmatched = [e for e in items if not e["factor_name"]]
    return {
        "summary": {
            "checklist_items": len(items),
            "matched_count": len(matched_names),
            "unmatched_count": len(unmatched),
            "gap_count": len(gaps),
            "matched_factors": matched_names,
            "methods": methods,
        },
        "items": items,
        "gaps": gaps,
        "matched": [e for e in items if e["factor_name"]],
        "unmatched": unmatched,
    }


def match_checklist_to_factors(
    items: list[ChecklistItem] | list[dict[str, str]],
    *,
    inventory_path: Path | None = None,
) -> list[FactorMatch]:
    """Resolve every checklist row to a Factor match (or unmatched / gated).

    One :class:`FactorMatch` is returned per input item so session audit trails
    can see coverage gaps. Callers that need unique Factor names should dedupe
    on ``factor_name``.

    When LLM factor matching is enabled, unmatched non-gated rows may be filled
    with ``match_method="llm_semantic"`` after the deterministic pass.
    """
    inv = str(inventory_path or DEFAULT_INVENTORY_PATH)
    factors = load_factor_names(inv)
    patterns = build_factor_patterns(inv)
    parsed: list[ChecklistItem] = []
    for row in items:
        if isinstance(row, ChecklistItem):
            parsed.append(row)
        else:
            parsed.append(ChecklistItem.model_validate(row))

    matches = [_match_item_to_factor(item, factors, patterns) for item in parsed]
    return llm_match_unmatched_factors(matches, factors)
