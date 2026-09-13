"""Tests for condition scoring and per-condition traversal grouping."""

from __future__ import annotations

from app.schemas import ChecklistItem
from app.services.graphrag.condition_ranker import score_conditions
from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.orchestrator import traverse_from_checklist


def _segment(
    *,
    factor: str,
    condition: str,
    relationship: str = "RISK_FACTOR_FOR",
    is_specific: bool = False,
) -> PathSegment:
    return PathSegment(
        factor=factor,
        factor_element_id=f"factor:{factor}",
        condition=condition,
        condition_element_id=f"condition:{condition}",
        relationship=relationship,
        relationship_element_id=f"rel:{factor}:{condition}",
        path_type="direct",
        via_mediation=False,
        is_specific=is_specific,
    )


def test_score_conditions_orders_by_weighted_evidence():
    segments = [
        _segment(factor="Fever", condition="Infection"),
        _segment(factor="Severe pain", condition="Fracture"),
        _segment(factor="Recent trauma", condition="Fracture", is_specific=True),
    ]
    risks = score_conditions(segments)
    assert [r.condition for r in risks] == ["Fracture", "Infection"]
    assert risks[0].risk_score > risks[1].risk_score
    assert risks[0].path_count == 2


def test_confirm_against_is_excluded_from_score():
    segments = [
        _segment(
            factor="Neuro sensory deficit",
            condition="CES",
            relationship="CONFIRM_AGAINST",
        ),
        _segment(
            factor="Fever",
            condition="Infection",
            relationship="SUGGESTIVE_OF",
        ),
    ]
    risks = score_conditions(segments)
    assert [r.condition for r in risks] == ["Infection"]
    assert all(r.condition != "CES" for r in risks)


def test_unilateral_sensory_does_not_rank_ces():
    items = [
        ChecklistItem(
            text="tingling down my leg",
            kind="symptom",
            source="gliner",
            label="symptom",
        ),
    ]
    trace = traverse_from_checklist(items, trace_id="confirm-against-ces")
    assert "Neuro sensory deficit" in trace.matched_factors
    assert "CES" not in trace.candidate_conditions
    assert any(
        s.relationship == "CONFIRM_AGAINST" and s.condition == "CES"
        for s in (
            step
            for step in trace.steps
            if step.relationship
        )
    )
    items = [
        ChecklistItem(
            text="severe pain",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
        ChecklistItem(
            text="had a recent fall last week",
            kind="symptom",
            source="gliner",
            label="symptom",
        ),
    ]
    trace = traverse_from_checklist(items, trace_id="grouped")
    assert trace.condition_risks
    assert trace.condition_traversals
    assert len(trace.condition_traversals) == len(trace.condition_risks)

    by_name = {t.condition: t for t in trace.condition_traversals}
    for risk in trace.condition_risks:
        traversal = by_name[risk.condition]
        assert traversal.risk_score == risk.risk_score
        assert traversal.rank >= 1
        assert any(
            s.action in ("traverse_direct", "traverse_mediated", "evidence_link")
            for s in traversal.steps
        )

    assert any(s.action == "match_factor" for s in trace.shared_steps)
    payload = trace.to_visualization_payload()
    assert payload["conditionTraversals"]
    assert payload["conditionRisks"]
