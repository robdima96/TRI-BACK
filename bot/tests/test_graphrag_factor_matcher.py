"""Tests for checklist → Factor matching (offline, no Neo4j)."""

from __future__ import annotations

import pytest

from app.schemas import ChecklistItem
from app.services.graphrag.factor_matcher import match_checklist_to_factors
from app.services.graphrag.orchestrator import traverse_from_checklist
from app.services.graphrag.schemas import FactorMatch, GraphTraversalTrace, TraversalStep


def test_match_severe_pain():
    items = [
        ChecklistItem(
            text="severe pain",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
    ]
    matches = match_checklist_to_factors(items)
    assert len(matches) == 1
    assert matches[0].factor_name == "Severe pain"
    assert matches[0].match_method in ("pattern_hint", "alias", "fuzzy", "exact", "checklist_kind", "regex", "factor_name_exact")


def test_match_mild_severity_does_not_map_to_severe():
    items = [
        ChecklistItem(
            text="mild",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
        ChecklistItem(
            text="3/10",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
        ChecklistItem(
            text="moderate",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
    ]
    matches = match_checklist_to_factors(items)
    assert all(m.factor_name is None for m in matches)


def test_match_numeric_severe_pain():
    items = [
        ChecklistItem(
            text="8/10",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
        ChecklistItem(
            text="7",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
    ]
    matches = match_checklist_to_factors(items)
    assert all(m.factor_name == "Severe pain" for m in matches)


def test_match_age_demographic():
    items = [
        ChecklistItem(text="70", kind="demographic", source="pattern", label="age"),
    ]
    matches = match_checklist_to_factors(items)
    assert matches[0].factor_name == "Age over 50"


def test_match_young_age_does_not_map_to_over_50():
    items = [
        ChecklistItem(text="30", kind="demographic", source="pattern", label="age"),
        ChecklistItem(text="45", kind="demographic", source="pattern", label="age"),
    ]
    matches = match_checklist_to_factors(items)
    assert all(m.factor_name is None for m in matches)


def test_factor_matching_audit_captures_gaps():
    from app.services.rag.factor_matcher import build_factor_matching_audit

    items = [
        ChecklistItem(text="30", kind="demographic", source="pattern", label="age"),
        ChecklistItem(
            text="mild",
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
        ChecklistItem(text="unrelated xyz", kind="other", source="pattern", label=""),
    ]
    matches = match_checklist_to_factors(items)
    audit = build_factor_matching_audit(matches)
    assert audit["summary"]["checklist_items"] == 4
    assert "Recent trauma" in audit["summary"]["matched_factors"]
    codes = {g["code"] for g in audit["gaps"]}
    assert "age_below_threshold" in codes
    assert "severity_below_threshold" in codes
    assert "unmatched" in codes
    assert any(e["status"] == "gated" for e in audit["items"])


def test_match_female_sex_demographic():
    items = [
        ChecklistItem(text="female", kind="demographic", source="pattern", label="sex"),
    ]
    matches = match_checklist_to_factors(items)
    assert len(matches) == 1
    assert matches[0].factor_name == "Female sex"
    assert matches[0].match_method == "checklist_kind"


def test_match_male_sex_demographic():
    items = [
        ChecklistItem(text="male", kind="demographic", source="pattern", label="sex"),
    ]
    matches = match_checklist_to_factors(items)
    assert len(matches) == 1
    assert matches[0].factor_name == "Male sex"
    assert matches[0].match_method == "checklist_kind"


def test_match_recent_trauma_alias():
    items = [
        ChecklistItem(
            text="had a recent fall last week",
            kind="symptom",
            source="gliner",
            label="symptom",
        ),
    ]
    matches = match_checklist_to_factors(items)
    assert matches[0].factor_name == "Recent trauma"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("my stomach really hurts", "Abdominal pain"),
        ("high blood pressure", "Hypertension"),
        ("sweating at night", "Night sweats"),
        ("both legs weak", "Bilat neuro motor deficit"),
        ("I smoke", "Smoking"),
        ("had a clot before", "Previous DVT"),
        ("shaking chills", "Chills"),
        ("tender to touch", "Point tenderness"),
        ("legs feel weak", "Neuro motor deficit"),
        ("family history of aneurysm", "Family history of AAA"),
    ],
)
def test_match_v3_colloquial_aliases(text: str, expected: str):
    items = [
        ChecklistItem(text=text, kind="symptom", source="gliner", label="symptom"),
    ]
    matches = match_checklist_to_factors(items)
    assert matches[0].factor_name == expected


def test_sitting_alias_stays_mechanical_not_venous_stasis():
    items = [
        ChecklistItem(
            text="sitting makes it worse",
            kind="provocative",
            source="pattern",
            label="provocative",
        ),
    ]
    matches = match_checklist_to_factors(items)
    assert matches[0].factor_name == "Prolonged sitting aggravates"


def test_match_fell_alias():
    items = [
        ChecklistItem(
            text="fell",
            kind="ner_entity",
            source="gliner",
            label="risk factor",
        ),
    ]
    matches = match_checklist_to_factors(items)
    assert matches[0].factor_name == "Recent trauma"


def test_match_mechanical_sitting_and_position_language():
    items = [
        ChecklistItem(text="male", kind="demographic", source="pattern", label="sex"),
        ChecklistItem(
            text="whenever i sit or lay down at night, i can really feel the pain more",
            kind="provocative",
            source="slot_answer",
            label="provocative",
        ),
        ChecklistItem(
            text="stretching seems to help, and changing position helps for a bit, then the pain is back",
            kind="palliative",
            source="slot_answer",
            label="palliative",
        ),
    ]
    matches = match_checklist_to_factors(items)
    names = {m.factor_name for m in matches if m.factor_name}
    assert "Male sex" in names
    assert "Prolonged sitting aggravates" in names
    assert names & {
        "Position change relief",
        "Improves with conservative care",
    }

    trace = traverse_from_checklist(items, trace_id="test-nsmc-surface")
    assert "Non-specific Mechanical Cause" in trace.candidate_conditions
    assert trace.candidate_conditions[0] == "Non-specific Mechanical Cause"


def test_traverse_offline_produces_steps():
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
        ChecklistItem(text="unrelated xyz", kind="other", source="pattern", label=""),
    ]
    trace = traverse_from_checklist(items, trace_id="test-offline")
    assert trace.trace_id == "test-offline"
    assert trace.mode == "traversal"
    assert any(s.action == "checklist_item" for s in trace.steps)
    assert any(s.action == "match_factor" for s in trace.steps)
    assert any(s.action == "unmatched" for s in trace.steps)
    assert "Severe pain" in trace.matched_factors
    assert "Recent trauma" in trace.matched_factors
    assert trace.model_dump()["highlight"]["node_ids"] == trace.highlight.node_ids


def _dumped_item(*, confirmed: bool) -> dict:
    return ChecklistItem(
        text="low back pain",
        kind="symptom",
        source="pattern",
        label="symptom",
        confirmed=confirmed,
    ).model_dump()


def test_factor_match_accepts_confirmed_bool():
    dumped = _dumped_item(confirmed=False)
    match = FactorMatch(checklist_item=dumped, match_method="none", match_score=0.0)
    assert match.checklist_item["confirmed"] is False

    dumped_yes = _dumped_item(confirmed=True)
    match_yes = FactorMatch(checklist_item=dumped_yes)
    assert match_yes.checklist_item["confirmed"] is True


def test_match_checklist_preserves_confirmed_bools():
    items = [
        ChecklistItem(
            text="30",
            kind="demographic",
            source="pattern",
            label="age",
            confirmed=False,
        ),
        ChecklistItem(
            text="low back pain",
            kind="symptom",
            source="gliner",
            label="symptom",
            confirmed=True,
        ),
    ]
    matches = match_checklist_to_factors(items)
    assert len(matches) == 2
    assert matches[0].checklist_item["confirmed"] is False
    assert matches[1].checklist_item["confirmed"] is True


def test_traversal_models_accept_confirmed_bool():
    dumped = _dumped_item(confirmed=False)
    step = TraversalStep(step=1, action="checklist_item", checklist_item=dumped)
    trace = GraphTraversalTrace(
        trace_id="t-confirmed",
        title="confirmed-bool",
        checklist_items=[dumped],
        unmatched_items=[dumped],
        steps=[step],
    )
    assert step.checklist_item["confirmed"] is False
    assert trace.checklist_items[0]["confirmed"] is False
    assert trace.unmatched_items[0]["confirmed"] is False
