"""Tests for graph-derived generator evidence."""

from __future__ import annotations

import pytest

from app.config import settings
from app.schemas import ChecklistItem, ChunkMatch
from app.services.graphrag.orchestrator import traverse_from_turn
from app.services.rag.evidence_builder import build_generator_evidence, evidence_from_trace


def test_evidence_from_ces_trace():
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
    trace = traverse_from_turn(checklist=items, chunk_matches=[], trace_id="ev-test")
    evidence = evidence_from_trace(trace)
    assert evidence
    joined = " ".join(e.snippet for e in evidence)
    assert "CES" in joined or any("CES" in e.source for e in evidence)
    assert any("->" in e.source or "factor:" in e.source for e in evidence)


def test_build_generator_evidence_graph_only(monkeypatch):
    monkeypatch.setattr(settings, "rag_load", False)
    monkeypatch.setattr(settings, "graphrag_load", True)
    trace = traverse_from_turn(
        checklist=[
            ChecklistItem(
                text="severe pain",
                kind="severity",
                source="pattern",
                label="symptom_severity",
            ),
        ],
        chunk_matches=[],
        trace_id="graph-only",
    )
    chroma_hit = ChunkMatch(
        chunk_id="r_99",
        source="chroma",
        snippet="should not appear",
        score=0.99,
        sub_collection="red_flags",
    )
    out = build_generator_evidence(trace=trace, chunk_matches=[chroma_hit])
    assert out
    assert not any(e.snippet == "should not appear" for e in out)


def test_build_generator_evidence_merges_both_paths(monkeypatch):
    monkeypatch.setattr(settings, "rag_load", True)
    monkeypatch.setattr(settings, "graphrag_load", True)
    trace = traverse_from_turn(
        checklist=[
            ChecklistItem(
                text="severe pain",
                kind="severity",
                source="pattern",
                label="symptom_severity",
            ),
        ],
        chunk_matches=[],
        trace_id="both-paths",
    )
    chroma_hit = ChunkMatch(
        chunk_id="r_5",
        source="2",
        snippet="Pain severity greater than 7/10",
        score=0.91,
        sub_collection="red_flags",
    )
    out = build_generator_evidence(trace=trace, chunk_matches=[chroma_hit])
    assert any(e.chunk_id == "r_5" for e in out)
    assert any("->" in e.source or "factor:" in e.source for e in out)
