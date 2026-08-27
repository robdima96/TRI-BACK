"""Authoritative disposition brief: graph rank + factor provenance for the generator."""

from __future__ import annotations

from typing import Any

# Suggested minimum triage level when a condition ranks first (heuristic rules engine).
_CONDITION_TRIAGE_LEVEL: dict[str, str] = {
    "CES": "emergency",
    "Cauda equina syndrome": "emergency",
    "AAA": "emergency",
    "Fracture": "urgent_care",
    "Infection": "urgent_care",
    "DVT": "urgent_care",
    "Malignancy": "urgent_care",
    "Non-specific Mechanical Cause": "routine_care",
}

_TRIAGE_SEVERITY_ORDER: tuple[str, ...] = (
    "self_care",
    "routine_care",
    "needs_assessment",
    "urgent_care",
    "emergency",
)

_CRITICAL_UNMATCHED_KINDS: frozenset[str] = frozenset(
    {"provocative", "severity", "comorbidity", "ner_entity"}
)

_TRAUMA_TEXT_HINTS: frozenset[str] = frozenset(
    {
        "fall",
        "fell",
        "trauma",
        "ladder",
        "accident",
        "injury",
    }
)


def _triage_rank(level: str) -> int:
    try:
        return _TRIAGE_SEVERITY_ORDER.index(level)
    except ValueError:
        return _TRIAGE_SEVERITY_ORDER.index("needs_assessment")


def _max_triage_level(*levels: str) -> str:
    if not levels:
        return "needs_assessment"
    return max(levels, key=_triage_rank)


def _parse_condition_risks(graph_traversal: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not graph_traversal:
        return []
    raw = graph_traversal.get("condition_risks")
    if raw is None:
        raw = graph_traversal.get("conditionRisks")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        condition = str(item.get("condition") or "").strip()
        if not condition:
            continue
        out.append(
            {
                "condition": condition,
                "score": float(item.get("risk_score") or item.get("riskScore") or 0.0),
                "path_count": int(item.get("path_count") or item.get("pathCount") or 0),
            }
        )
    return out


def _evidence_factors_from_audit(
    factor_matching_audit: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not factor_matching_audit:
        return []
    out: list[dict[str, Any]] = []
    for entry in factor_matching_audit.get("matched") or []:
        if not isinstance(entry, dict):
            continue
        factor = str(entry.get("factor_name") or "").strip()
        if not factor:
            continue
        item = entry.get("checklist_item") or {}
        out.append(
            {
                "factor": factor,
                "checklist_id": str(item.get("id") or ""),
                "checklist_text": str(item.get("text") or ""),
                "match_method": str(entry.get("match_method") or ""),
                "match_score": float(entry.get("match_score") or 0.0),
            }
        )
    return out


def _unmatched_rows_from_audit(
    factor_matching_audit: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not factor_matching_audit:
        return []
    out: list[dict[str, Any]] = []
    for entry in factor_matching_audit.get("unmatched") or []:
        if not isinstance(entry, dict):
            continue
        item = entry.get("checklist_item") or {}
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "text": text,
                "kind": str(item.get("kind") or ""),
                "label": str(item.get("label") or ""),
                "checklist_id": str(item.get("id") or ""),
            }
        )
    return out


def _is_critical_unmatched(row: dict[str, Any]) -> bool:
    kind = str(row.get("kind") or "").casefold()
    text = str(row.get("text") or "").casefold()
    if kind in _CRITICAL_UNMATCHED_KINDS and any(h in text for h in _TRAUMA_TEXT_HINTS):
        return True
    if kind == "provocative":
        return True
    return False


def build_disposition_brief(
    *,
    graph_traversal: dict[str, Any] | None,
    factor_matching_audit: dict[str, Any] | None,
    clinical_checklist: list[dict[str, Any]] | None = None,
    candidate_conditions: list[str] | None = None,
    matched_factors: list[str] | None = None,
    inference_mode: str = "deterministic",
) -> dict[str, Any]:
    """
    Build a machine-readable brief from graph traversal output and factor audit.

    The generator must treat ``primary_condition`` and ``minimum_triage_level``
    as authoritative unless ``insufficient_evidence`` is true.
    """
    _ = clinical_checklist  # reserved for future graph-coverage gates
    ranked = _parse_condition_risks(graph_traversal)
    if not ranked and candidate_conditions:
        ranked = [
            {"condition": name, "score": float(len(candidate_conditions) - i), "path_count": 0}
            for i, name in enumerate(candidate_conditions)
        ]

    primary = ranked[0]["condition"] if ranked else None
    primary_score = ranked[0]["score"] if ranked else 0.0

    evidence_factors = _evidence_factors_from_audit(factor_matching_audit)
    unmatched_rows = _unmatched_rows_from_audit(factor_matching_audit)
    critical_unmatched = [r for r in unmatched_rows if _is_critical_unmatched(r)]

    levels: list[str] = []
    if primary:
        levels.append(_CONDITION_TRIAGE_LEVEL.get(primary, "needs_assessment"))
    for factor in matched_factors or []:
        for cond, level in _CONDITION_TRIAGE_LEVEL.items():
            if cond.casefold() in factor.casefold():
                levels.append(level)
    minimum_triage_level = _max_triage_level(*levels) if levels else "needs_assessment"

    insufficient = bool(critical_unmatched) or (not primary and not (matched_factors or []))

    if insufficient:
        minimum_triage_level = _max_triage_level(minimum_triage_level, "needs_assessment")

    summary_parts: list[str] = []
    if primary:
        summary_parts.append(
            f"Graph rank #1 is {primary} (score {primary_score:.1f})."
        )
    if matched_factors:
        summary_parts.append(f"Matched factors: {', '.join(matched_factors)}.")
    if critical_unmatched:
        summary_parts.append(
            f"{len(critical_unmatched)} checklist row(s) did not map to graph factors."
        )
    if not summary_parts:
        summary_parts.append("No ranked conditions; use conservative triage wording.")

    return {
        "inference_mode": inference_mode,
        "primary_condition": primary,
        "primary_score": round(primary_score, 3),
        "ranked_conditions": ranked,
        "matched_factors": list(matched_factors or []),
        "evidence_factors": evidence_factors,
        "unmatched_checklist_rows": unmatched_rows,
        "critical_unmatched_rows": critical_unmatched,
        "minimum_triage_level": minimum_triage_level,
        "insufficient_evidence": insufficient,
        "authoritative_summary": " ".join(summary_parts),
    }


def format_brief_for_prompt(brief: dict[str, Any] | None) -> str:
    """Render the brief as a prompt block for disposition generation."""
    if not brief:
        return ""

    lines = [
        "Graph disposition brief (AUTHORITATIVE — follow this for triage level and primary condition):",
        f"- Summary: {brief.get('authoritative_summary', '')}",
        f"- Primary condition: {brief.get('primary_condition') or '(none ranked)'}",
        f"- Primary score: {brief.get('primary_score', 0)}",
        f"- Minimum triage level: {brief.get('minimum_triage_level', 'needs_assessment')}",
        f"- Insufficient structured evidence: {bool(brief.get('insufficient_evidence'))}",
    ]

    ranked = brief.get("ranked_conditions") or []
    if ranked:
        ranked_text = ", ".join(
            f"{r.get('condition')} ({float(r.get('score', 0)):.1f})" for r in ranked[:6]
        )
        lines.append(f"- Ranked conditions: {ranked_text}")

    factors = brief.get("matched_factors") or []
    if factors:
        lines.append(f"- Matched graph factors: {', '.join(factors)}")

    evidence = brief.get("evidence_factors") or []
    if evidence:
        prov = "; ".join(
            f"{e.get('factor')}←{e.get('checklist_text')!r}" for e in evidence[:8]
        )
        lines.append(f"- Factor provenance: {prov}")

    lines.extend(
        [
            "- You MUST explain the primary condition using the matched factors above.",
            "- Do NOT base disposition primarily on a lower-ranked condition.",
            "- Conversation history is for tone and quotes only; do not override this brief.",
        ]
    )
    if brief.get("insufficient_evidence"):
        lines.append(
            "- Evidence is incomplete: recommend in-person assessment and note unmatched findings."
        )

    return "\n".join(lines)


def build_disposition_brief_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Build a brief from orchestrator ``ChatState`` fields after graph traversal."""
    graph = state.get("graph_traversal")
    inference = "deterministic"
    if isinstance(graph, dict):
        inference = str(graph.get("inference") or inference)
    return build_disposition_brief(
        graph_traversal=graph if isinstance(graph, dict) else None,
        factor_matching_audit=state.get("factor_matching_audit"),
        clinical_checklist=state.get("clinical_checklist") or [],
        candidate_conditions=state.get("candidate_conditions"),
        matched_factors=state.get("matched_factors"),
        inference_mode=inference,
    )
