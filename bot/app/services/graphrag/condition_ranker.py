"""Rank candidate Conditions from local graph path segments."""

from __future__ import annotations

from collections import defaultdict

from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.schemas import ConditionRisk

_CONDITION_PRIORITY: dict[str, float] = {
    "CES": 5.0,
    "AAA": 4.5,
    "Infection": 4.0,
    "Non-specific Mechanical Cause": 4.0,
    "DVT": 3.5,
    "Malignancy": 3.0,
    "Fracture": 2.0,
}

_REL_WEIGHT: dict[str, float] = {
    "TRIGGER_FOR": 2.0,
    "SUGGESTIVE_OF": 1.5,
    "RISK_FACTOR_FOR": 1.0,
    "ASSOCIATED_WITH": 0.8,
    "CONTRIBUTES_TO": 1.0,
}

# "Ask about this" edges. Keep them in traversal / coverage / neighbourhood;
# never feed them to score() or a policy/escalation gate.
NON_SCORING_RELATIONSHIPS: frozenset[str] = frozenset({"CONFIRM_AGAINST"})


def _rel_key(relationship: str) -> str:
    return relationship.strip().upper().replace(" ", "_").replace("-", "_")


def is_scoring_relationship(relationship: str) -> bool:
    """False for CONFIRM_AGAINST: a reason to ask, never a reason to rank or escalate."""
    return _rel_key(relationship) not in NON_SCORING_RELATIONSHIPS


def scoring_segments(segments: list[PathSegment]) -> list[PathSegment]:
    """Drop CONFIRM_AGAINST (and any other non-scoring) edges before risk aggregation."""
    return [seg for seg in segments if is_scoring_relationship(seg.relationship)]


def _segment_score(seg: PathSegment) -> float:
    rel_key = _rel_key(seg.relationship)
    rel_w = _REL_WEIGHT.get(rel_key, 0.5)
    if rel_key == "CONTRIBUTES_TO":
        rel_w = _REL_WEIGHT["CONTRIBUTES_TO"]
    specific_bonus = 1.5 if seg.is_specific else 1.0
    base = _CONDITION_PRIORITY.get(seg.condition, 1.0)
    return base * rel_w * specific_bonus


def score_conditions(segments: list[PathSegment]) -> list[ConditionRisk]:
    """Return ranked conditions with aggregated path evidence scores.

    CONFIRM_AGAINST segments are ignored here. They remain in traversal so
    neighbourhood / coverage still see the hop (e.g. tingling → CES).
    """
    scores: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for seg in scoring_segments(segments):
        if not seg.condition:
            continue
        scores[seg.condition] += _segment_score(seg)
        counts[seg.condition] += 1

    ordered = sorted(scores.keys(), key=lambda c: (-scores[c], c))
    return [
        ConditionRisk(
            condition=cond,
            risk_score=round(scores[cond], 3),
            path_count=counts[cond],
        )
        for cond in ordered
    ]


def rank_conditions(segments: list[PathSegment]) -> list[str]:
    """Return condition names sorted by aggregated path evidence score."""
    return [risk.condition for risk in score_conditions(segments)]
