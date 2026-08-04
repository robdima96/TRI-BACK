"""Arm 2: chain-of-thought reasoning from GraphTraversalTrace.

Builds a short patient-facing narrative from matched factors and the top
condition paths. Intentionally omits raw checklist dumps, chunk ids,
Cypher-style edge strings, and citation inventories (those belong in
session JSON / Arm 3 graph debug — not the CoT panel).
"""

from __future__ import annotations

import re

from digimsk_study_app.graph.schemas import (
    ConditionTraversal,
    GraphTraversalTrace,
    TraversalStep,
)

_MAX_CONDITIONS = 3
_MAX_RATIONALE_PER_CONDITION = 3

_REL_PHRASE = {
    "RISK_FACTOR_FOR": "increases risk for",
    "ASSOCIATED_WITH": "is associated with",
    "SUGGESTIVE_OF": "is suggestive of",
    "TRIGGER_FOR": "can trigger concern for",
    "CONTRIBUTES_TO": "contributes to",
}

_CHUNK_ID_NOTE = re.compile(r"^r_\d+", re.I)


def _join_and(parts: list[str]) -> str:
    items = [p for p in parts if p]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _plain_evidence_note(step: TraversalStep) -> str | None:
    """Prefer prose evidence notes over technical traversal artifacts."""
    if step.action != "evidence_link":
        return None
    note = (step.note or "").strip()
    if not note or _CHUNK_ID_NOTE.match(note):
        return None
    if "-[" in note:
        return None
    # Trim mid-sentence truncation left by orchestrator snippet cuts.
    note = note.rstrip()
    if len(note) > 180:
        note = note[:177].rstrip() + "…"
    return note


def _plain_path_link(step: TraversalStep) -> str | None:
    if step.action not in ("traverse_direct", "traverse_mediated"):
        return None
    if not step.factor or not step.condition:
        return None
    rel = _REL_PHRASE.get((step.relationship or "").upper(), "relates to")
    if step.mediator and step.action == "traverse_mediated":
        return (
            f"{step.factor} {rel} {step.condition} "
            f"(pathway involves {step.mediator})"
        )
    return f"{step.factor} {rel} {step.condition}"


def _condition_rationale(traversal: ConditionTraversal) -> str:
    """2–3 plain-English reasons for why this condition is under consideration."""
    pieces: list[str] = []
    seen: set[str] = set()

    for step in traversal.steps:
        note = _plain_evidence_note(step)
        if note and note.casefold() not in seen:
            seen.add(note.casefold())
            pieces.append(note)
        if len(pieces) >= _MAX_RATIONALE_PER_CONDITION:
            break

    if len(pieces) < _MAX_RATIONALE_PER_CONDITION:
        for step in traversal.steps:
            link = _plain_path_link(step)
            if link and link.casefold() not in seen:
                # Prefer links that involve already-matched supporting factors.
                if (
                    traversal.supporting_factors
                    and step.factor
                    and step.factor not in traversal.supporting_factors
                ):
                    continue
                seen.add(link.casefold())
                pieces.append(link)
            if len(pieces) >= _MAX_RATIONALE_PER_CONDITION:
                break

    if not pieces and traversal.supporting_factors:
        factors = _join_and(list(traversal.supporting_factors)[:4])
        return (
            f"Supporting red-flag factors for this concern include {factors}."
        )
    if not pieces:
        return "This condition shares red-flag markers present in the intake."
    if len(pieces) == 1:
        return pieces[0]
    return " ".join(pieces)


def format_reasoning_steps(
    trace: GraphTraversalTrace | None,
    citations: list[dict] | None = None,
) -> list[str]:
    """Return ordered CoT sentences. ``citations`` is accepted for API
    compatibility but intentionally unused (avoids dumping chunk inventories).
    """
    del citations  # session/UI citations stay elsewhere; not CoT content
    if trace is None:
        return []

    steps: list[str] = []
    factors = [f for f in (trace.matched_factors or []) if f]
    if factors:
        steps.append(
            "From what you shared, these red-flag factors were identified: "
            f"{_join_and(factors)}."
        )
    else:
        steps.append(
            "I reviewed your symptoms against the red-flag knowledge graph "
            "to look for urgent triage concerns."
        )

    traversals = sorted(
        trace.condition_traversals or [],
        key=lambda t: (t.rank, -t.risk_score),
    )[:_MAX_CONDITIONS]

    if traversals:
        top = traversals[0]
        steps.append(
            f"The leading triage concern is {top.condition}. "
            f"{_condition_rationale(top)}"
        )
        others = traversals[1:]
        if others:
            names = _join_and([t.condition for t in others])
            steps.append(
                f"Other conditions also considered, at lower priority, were "
                f"{names}."
            )
    elif trace.candidate_conditions:
        steps.append(
            "Candidate conditions flagged for triage consideration were "
            f"{_join_and(list(trace.candidate_conditions)[:_MAX_CONDITIONS])}."
        )

    steps.append(
        "This reasoning supports the triage recommendation above and is not "
        "a diagnosis."
    )
    return steps


def reasoning_text(
    trace: GraphTraversalTrace | None,
    citations: list[dict] | None = None,
) -> str:
    lines = format_reasoning_steps(trace, citations)
    if not lines:
        return ""
    return "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))
