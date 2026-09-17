"""Disposition seeds from factor_states; agentic tools fail closed on rematch."""

from __future__ import annotations

import pytest

from app.schemas import ChecklistItem
from app.services.agentic_graph_rag.ontology import RedFlagOntology
from app.services.agentic_graph_rag.tools import (
    PrecomputedFactorMatchRequired,
    ToolContext,
    tool_get_matched_factors,
)
from app.services.graphrag.orchestrator import traverse_from_turn
from app.services.rag.fusion import build_disposition_seeds
from app.services.rag.factor_matcher import factor_matches_from_states


def test_palliative_exercise_leftover_does_not_become_onset():
    states = {"Improves with conservative care": "affirmed"}
    checklist = [
        ChecklistItem(
            text="exercise",
            kind="palliative",
            source="slot_answer",
            label="palliative",
        ),
        ChecklistItem(
            text="heavy lifting at work today",
            kind="provocative",
            source="user_message",
            label="provocative",
        ),
    ]
    seeds, filled, leftover = build_disposition_seeds(
        factor_states=states,
        checklist=checklist,
    )
    leftover_names = {
        m.factor_name for m in leftover if m.factor_name and m.polarity != "denied"
    }
    assert "Activity-related onset" not in leftover_names
    assert filled["Improves with conservative care"] == "affirmed"
    affirmed = {m.factor_name for m in seeds.factor_matches if m.polarity == "affirmed"}
    assert "Improves with conservative care" in affirmed
    assert "Activity-related onset" not in affirmed


def test_synth_seeds_from_states_exclude_unknown():
    matches = factor_matches_from_states(
        {
            "Male sex": "affirmed",
            "Severe pain": "denied",
            "Saddle anaesthesia": "unknown",
        }
    )
    by_name = {m.factor_name: m.polarity for m in matches}
    assert by_name["Male sex"] == "affirmed"
    assert by_name["Severe pain"] == "denied"
    assert "Saddle anaesthesia" not in by_name


def test_traverse_from_turn_empty_list_does_not_rematch():
    items = [
        ChecklistItem(
            text="fever",
            kind="ner_entity",
            source="test",
            label="symptom",
        )
    ]
    trace = traverse_from_turn(checklist=items, factor_matches=[])
    assert trace.matched_factors == []


def _empty_ontology() -> RedFlagOntology:
    return RedFlagOntology(
        graph_version="test",
        conditions=("CES",),
        factors_by_condition={"CES": ("Saddle anaesthesia",)},
        mediators=(),
        relations=(),
        all_factors=("Saddle anaesthesia",),
    )


def test_get_matched_factors_uses_precomputed():
    ctx = ToolContext(
        checklist=[],
        chunk_matches=[],
        ontology=_empty_ontology(),
        precomputed_matched_factors=["Saddle anaesthesia"],
        precomputed_factor_matches=[],
    )
    result = tool_get_matched_factors(ctx)
    assert result.factors == ["Saddle anaesthesia"]
    assert result.data["source"] == "precomputed_traversal"


def test_get_matched_factors_fails_closed_without_precomputed():
    ctx = ToolContext(
        checklist=[
            ChecklistItem(
                text="fever",
                kind="ner_entity",
                source="test",
                label="symptom",
            ).model_dump()
        ],
        chunk_matches=[],
        ontology=_empty_ontology(),
    )
    with pytest.raises(PrecomputedFactorMatchRequired):
        tool_get_matched_factors(ctx)
