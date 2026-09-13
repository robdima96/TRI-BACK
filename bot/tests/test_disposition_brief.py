"""Disposition brief: graph rank binding for generator."""

from __future__ import annotations

from app.services.disposition_brief import (
    build_disposition_brief,
    build_disposition_brief_from_state,
    format_brief_for_prompt,
)


def test_build_disposition_brief_ranks_primary_condition():
    graph = {
        "condition_risks": [
            {"condition": "Fracture", "risk_score": 8.5, "path_count": 2},
            {"condition": "Non-specific Mechanical Cause", "risk_score": 1.2, "path_count": 1},
        ],
    }
    audit = {
        "matched": [
            {
                "factor_name": "Recent trauma",
                "match_method": "exact",
                "match_score": 1.0,
                "checklist_item": {
                    "id": "cl_tr",
                    "text": "fell from ladder",
                    "kind": "provocative",
                    "label": "provocative",
                },
            }
        ],
        "unmatched": [],
    }
    brief = build_disposition_brief(
        graph_traversal=graph,
        factor_matching_audit=audit,
        matched_factors=["Recent trauma"],
    )
    assert brief["primary_condition"] == "Fracture"
    assert brief["minimum_triage_level"] == "urgent_care"
    assert brief["insufficient_evidence"] is False
    assert brief["evidence_factors"][0]["checklist_text"] == "fell from ladder"


def test_build_disposition_brief_flags_critical_unmatched():
    audit = {
        "matched": [],
        "unmatched": [
            {
                "checklist_item": {
                    "id": "cl_fall",
                    "text": "fell from ladder",
                    "kind": "provocative",
                    "label": "provocative",
                }
            }
        ],
    }
    brief = build_disposition_brief(
        graph_traversal=None,
        factor_matching_audit=audit,
        matched_factors=[],
    )
    assert brief["insufficient_evidence"] is True
    assert len(brief["critical_unmatched_rows"]) == 1


def test_format_brief_for_prompt_includes_authoritative_instructions():
    brief = build_disposition_brief(
        graph_traversal={
            "condition_risks": [{"condition": "CES", "risk_score": 9.0, "path_count": 1}],
        },
        factor_matching_audit={"matched": [], "unmatched": []},
        matched_factors=["Saddle anesthesia"],
    )
    text = format_brief_for_prompt(brief)
    assert "AUTHORITATIVE" in text
    assert "Primary condition: CES" in text
    assert "Minimum triage level: emergency" in text
    assert "Do NOT base disposition primarily on a lower-ranked condition" in text


def test_build_disposition_brief_time_critical_unknown_is_not_self_care():
    from app.orchestrator.question_planner import INSUFFICIENT_INFO_REASON

    brief = build_disposition_brief(
        graph_traversal={
            "condition_risks": [
                {"condition": "Non-specific Mechanical Cause", "risk_score": 2.0, "path_count": 1},
            ],
        },
        factor_matching_audit={"matched": [], "unmatched": []},
        matched_factors=["Neuro sensory deficit"],
        question_reason=INSUFFICIENT_INFO_REASON,
    )
    assert brief["insufficient_evidence"] is True
    assert brief["time_critical_unknown"] is True
    text = format_brief_for_prompt(brief)
    assert "Not enough information to advise" in text
    assert "Do NOT recommend self-care" in text


def test_build_disposition_brief_from_state():
    state = {
        "graph_traversal": {
            "inference": "deterministic",
            "condition_risks": [
                {"condition": "Infection", "risk_score": 4.0, "path_count": 1},
            ],
        },
        "factor_matching_audit": {"matched": [], "unmatched": []},
        "clinical_checklist": [],
        "candidate_conditions": ["Infection"],
        "matched_factors": ["Fever"],
    }
    brief = build_disposition_brief_from_state(state)
    assert brief["primary_condition"] == "Infection"
    assert brief["inference_mode"] == "deterministic"
