"""Arm-3 intake planner slice + schema literals used by bot and study app."""

from __future__ import annotations

from pathlib import Path

from typing import get_args

from app.orchestrator.nodes import finalize_response_node, generate_question_node
from app.services.agentic_graph_rag.ontology import load_ontology
from app.services.disposition_brief import INSUFFICIENT_INFO_TEXT, decline_to_advise_text
from app.services.graphrag.intake_traversal import (
    allowed_intake_edge_types,
    assert_intake_edges_are_csv_backed,
    build_intake_gap_trace,
    final_intake_trace_from_state,
    highlighted_factor_names,
)
from app.services.graphrag.schemas import TraversalAction, TraversalMode
from app.services.policy import RISK_CATALOG, apply_policy
from app.session_enrichment import build_disposition_record, build_intake_record


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_SCHEMA = REPO_ROOT / "bot" / "app" / "services" / "graphrag" / "schemas.py"
STUDY_SCHEMA = (
    REPO_ROOT
    / "prototypes"
    / "tri_back_study_app"
    / "tri_back_study_app"
    / "graph"
    / "schemas.py"
)


def _literal_names(path: Path, assignment: str) -> tuple[str, ...]:
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == assignment for t in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Tuple):
            return tuple(
                elt.value
                for elt in value.slice.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )
    raise AssertionError(f"{assignment} not found in {path}")


def test_traversal_action_literals_match_study_app():
    assert _literal_names(BOT_SCHEMA, "TraversalAction") == _literal_names(
        STUDY_SCHEMA, "TraversalAction"
    )
    assert "ask_factor" in get_args(TraversalAction)
    assert "deny_factor" in get_args(TraversalAction)
    assert "graph_gap" in get_args(TraversalAction)


def test_traversal_mode_literals_match_study_app():
    assert _literal_names(BOT_SCHEMA, "TraversalMode") == _literal_names(
        STUDY_SCHEMA, "TraversalMode"
    )
    assert get_args(TraversalMode) == ("traversal", "intake_gap")


def test_intake_gap_highlights_ask_target_from_question_reason():
    reason = "rank:t1:CES:Saddle anaesthesia"
    trace = build_intake_gap_trace(
        factor_states={"Neuro sensory deficit": "affirmed", "Bladder dysfunction": "denied"},
        asked_factor="Saddle anaesthesia",
        question_reason=reason,
    )
    assert trace.mode == "intake_gap"
    assert_intake_edges_are_csv_backed(trace)
    assert "Saddle anaesthesia" in highlighted_factor_names(trace)
    ask_steps = [s for s in trace.steps if s.action == "ask_factor"]
    assert ask_steps
    assert reason in (ask_steps[0].note or "")
    denied = [
        n for n in trace.nodes if n.label == "Factor" and n.name == "Bladder dysfunction"
    ]
    assert denied
    assert denied[0].properties.get("polarity") == "denied"
    confirm = [e for e in trace.edges if e.type == "CONFIRM_AGAINST"]
    assert confirm
    forbidden = {"askable", "intent", "fallback", "synonyms", "DESCRIBES", "APPLIES_TO"}
    assert not ({e.type for e in trace.edges} & forbidden)
    assert {e.type for e in trace.edges} <= allowed_intake_edge_types()


def test_intake_gap_does_not_highlight_non_askable_mediator():
    ont = load_ontology()
    spec = ont.get_factor_question_spec("Endothelial injury")
    assert spec is None or not spec.askable
    trace = build_intake_gap_trace(
        factor_states={"Calf pain": "affirmed"},
        asked_factor="Endothelial injury",
        question_reason="rank:t1:DVT:Endothelial injury",
    )
    assert highlighted_factor_names(trace) == []


def test_generate_question_writes_intake_and_clears_disposition_graph():
    state = {
        "session_id": "intake-view",
        "next_question": "Any numbness in the saddle area?",
        "question_reason": "rank:t1:CES:Saddle anaesthesia",
        "asked_factor": "Saddle anaesthesia",
        "slot_being_asked": None,
        "questions_asked": 0,
        "factor_states": {"Neuro sensory deficit": "affirmed"},
        "graph_traversal": {"trace_id": "old-disp", "mode": "traversal"},
        "matched_factors": ["Neuro sensory deficit"],
        "candidate_conditions": ["CES"],
        "traversed_chunk_ids": ["r_45"],
        "factor_matching_audit": {"summary": {}},
        "agent_trace": {"status": "ok"},
    }
    out = generate_question_node(state)
    assert out["graph_traversal"] is None
    assert out["matched_factors"] == []
    intake = out.get("intake_traversal") or {}
    assert intake.get("mode") == "intake_gap"
    assert intake.get("trace_id") != "old-disp"
    factors = {n["name"] for n in intake.get("nodes") or [] if n.get("label") == "Factor"}
    assert "Saddle anaesthesia" in factors


def test_disposition_and_intake_records_do_not_overwrite():
    question_state = {
        "question_mode": True,
        "question_reason": "rank:t1:CES:Saddle anaesthesia",
        "asked_factor": "Saddle anaesthesia",
        "factor_states": {"Neuro sensory deficit": "affirmed"},
        "intake_traversal": {"mode": "intake_gap", "trace_id": "in1", "steps": []},
    }
    intake = build_intake_record(question_state, turn_index=2)
    assert intake is not None
    assert intake["asked_factor"] == "Saddle anaesthesia"
    assert build_disposition_record(question_state, turn_index=2) is None

    disp_state = {
        "question_mode": False,
        "graph_traversal": {"mode": "traversal", "trace_id": "disp1"},
        "matched_factors": ["Neuro sensory deficit"],
        "intake_traversal": {"mode": "intake_gap", "trace_id": "in1"},
        "final_response": "Seek in-person care.",
    }
    disposition = build_disposition_record(disp_state, turn_index=3)
    assert disposition is not None
    assert disposition["graph_traversal"]["trace_id"] == "disp1"
    assert disposition["intake_traversal"]["trace_id"] == "in1"
    assert build_intake_record(disp_state, turn_index=3) is None


def test_final_intake_trace_has_no_ask_target():
    trace = final_intake_trace_from_state(
        {
            "session_id": "final-path",
            "factor_states": {
                "Neuro sensory deficit": "affirmed",
                "Saddle anaesthesia": "denied",
            },
            "asked_factor": "Saddle anaesthesia",
            "question_reason": "rank:t1:CES:Saddle anaesthesia",
        }
    )
    assert trace.mode == "intake_gap"
    assert_intake_edges_are_csv_backed(trace)
    assert highlighted_factor_names(trace) == []
    saddle = next(n for n in trace.nodes if n.label == "Factor" and n.name == "Saddle anaesthesia")
    assert saddle.properties.get("ask_target") is False
    assert saddle.properties.get("polarity") == "denied"
    assert not any(s.action == "ask_factor" for s in trace.shared_steps)


def test_finalize_rebuilds_intake_without_ask_target():
    out = finalize_response_node(
        {
            "session_id": "final-intake",
            "question_mode": False,
            "final_response": "Seek in-person care.",
            "factor_states": {
                "Neuro sensory deficit": "affirmed",
                "Saddle anaesthesia": "denied",
            },
            "asked_factor": "Saddle anaesthesia",
            "question_reason": "rank:t1:CES:Saddle anaesthesia",
            "intake_traversal": {"trace_id": "stale-ask", "mode": "intake_gap"},
        }
    )
    intake = out.get("intake_traversal") or {}
    assert intake.get("mode") == "intake_gap"
    assert intake.get("trace_id") != "stale-ask"
    factors = {
        n["name"]: n.get("properties") or {}
        for n in intake.get("nodes") or []
        if n.get("label") == "Factor"
    }
    assert factors["Saddle anaesthesia"].get("ask_target") is False
    assert factors["Saddle anaesthesia"].get("polarity") == "denied"
    assert not any(
        s.get("action") == "ask_factor" for s in intake.get("shared_steps") or []
    )


def test_finalize_does_not_overwrite_intake_on_question_turn():
    out = finalize_response_node(
        {
            "question_mode": True,
            "final_response": "Any numbness in the saddle area?",
            "intake_traversal": {"trace_id": "keep-ask"},
        }
    )
    assert "intake_traversal" not in out


def test_policy_catalog_excludes_lbp_red_flags():
    assert set(RISK_CATALOG) == {
        "suicide_self_harm",
        "chest_pain",
        "respiratory_distress",
    }
    escalated, reason, _ = apply_policy("Self-care is reasonable.", [])
    assert escalated is False
    assert reason is None


def test_affirmed_saddle_does_not_policy_escalate():
    """LBP red flags stay with the disposition model, not RISK_CATALOG."""
    from langchain_core.messages import HumanMessage

    from app.orchestrator.graph import build_chat_graph

    graph = build_chat_graph()
    state = graph.invoke(
        {
            "session_id": "saddle-no-policy",
            "messages": [HumanMessage(content="I have saddle numbness")],
        },
        {"configurable": {"thread_id": "saddle-no-policy"}},
    )
    assert state.get("escalated") is False
    assert (state.get("factor_states") or {}).get("Saddle anaesthesia") == "affirmed"


def test_decline_to_advise_uses_canned_copy_not_llm():
    from app.orchestrator.question_planner import INSUFFICIENT_INFO_REASON
    from app.services.disposition_brief import build_disposition_brief
    from app.services.generator import generate_response

    brief = build_disposition_brief(
        graph_traversal={
            "condition_risks": [
                {"condition": "Non-specific Mechanical Cause", "risk_score": 2.0}
            ]
        },
        factor_matching_audit={"matched": [], "unmatched": []},
        matched_factors=["Neuro sensory deficit"],
        question_reason=INSUFFICIENT_INFO_REASON,
    )
    assert brief["decline_to_advise"] is True
    assert decline_to_advise_text(brief) == INSUFFICIENT_INFO_TEXT
    text = generate_response("low back pain", [], disposition_brief=brief)
    assert text == INSUFFICIENT_INFO_TEXT
    assert "self-care" not in text.casefold() or "don't have enough" in text.casefold()
