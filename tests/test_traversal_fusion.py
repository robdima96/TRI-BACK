"""Tests for traverse_from_turn fusion."""

from __future__ import annotations

from app.schemas import ChecklistItem, ChunkMatch
from app.services.graphrag.orchestrator import traverse_from_turn


def test_ces_candidates_from_checklist():
    items = [
        ChecklistItem(
            text="bladder control problems",
            kind="symptom",
            source="gliner",
            label="symptom",
        ),
        ChecklistItem(
            text="saddle numbness",
            kind="symptom",
            source="gliner",
            label="symptom",
        ),
    ]
    trace = traverse_from_turn(
        checklist=items,
        chunk_matches=[],
        trace_id="ces-test",
    )
    assert any(s.action == "match_factor" for s in trace.steps)
    assert "CES" in trace.candidate_conditions


def test_traverse_with_chunk_match():
    items = [
        ChecklistItem(
            text="severe pain",
            kind="severity",
            source="pattern",
            label="symptom_severity",
        ),
    ]
    chunks = [
        ChunkMatch(
            chunk_id="r_5",
            source="2",
            snippet="Pain severity greater than 7/10",
            score=0.9,
            sub_collection="red_flags",
        )
    ]
    trace = traverse_from_turn(
        checklist=items,
        chunk_matches=chunks,
        trace_id="chunk-seed",
    )
    assert any(s.action == "match_chunk" for s in trace.steps)
    assert "Fracture" in trace.candidate_conditions
    assert trace.nodes
    assert trace.edges
    assert trace.condition_traversals
