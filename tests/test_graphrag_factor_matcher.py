"""Tests for checklist → Factor matching (offline, no Neo4j)."""

from __future__ import annotations

from app.schemas import ChecklistItem
from app.services.graphrag.factor_matcher import match_checklist_to_factors
from app.services.graphrag.orchestrator import traverse_from_checklist


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


def test_match_age_demographic():
    items = [
        ChecklistItem(text="70", kind="demographic", source="pattern", label="age"),
    ]
    matches = match_checklist_to_factors(items)
    assert matches[0].factor_name == "Age over 50"


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
