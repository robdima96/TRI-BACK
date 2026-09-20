"""Post-disposition dormant phase and durable session resume."""

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage

from app.orchestrator.dormant import (
    DORMANT_PHASE,
    DORMANT_REPLY,
    INTAKE_PHASE,
    detect_symptom_change,
)
from app.orchestrator.graph import build_chat_graph
from app.orchestrator.messages import transcript_from_messages, user_message_count
from app.orchestrator.session_resume import resume_values_from_session
from app.session_enrichment import (
    build_disposition_record,
    build_orchestrator_snapshot,
    exposed_chat_graph_fields,
)
from app.session_store import load_session, merge_session_fields, save_session


def test_detect_change_ignores_question_mark():
    assert (
        detect_symptom_change(
            message="?",
            prior_checklist=[{"text": "back", "kind": "ner_entity", "source": "gliner", "label": "body part"}],
            merged_checklist=[{"text": "back", "kind": "ner_entity", "source": "gliner", "label": "body part"}],
        )
        is False
    )


def test_detect_change_yes_and_new_symptom_row():
    assert detect_symptom_change(
        message="yes",
        prior_checklist=[],
        merged_checklist=[],
    )
    prior = [{"text": "back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"}]
    merged = prior + [
        {"text": "leg pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"}
    ]
    assert detect_symptom_change(
        message="Pain is now going down my leg",
        prior_checklist=prior,
        merged_checklist=merged,
    )


def test_dormant_question_mark_is_canned_and_keeps_checklist():
    graph = build_chat_graph()
    config = {"configurable": {"thread_id": "dorm-1"}}
    checklist = [
        {"text": "60", "kind": "demographic", "source": "pattern", "label": "age"},
        {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        {"text": "back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
    ]
    graph.update_state(
        config,
        {
            "session_id": "dorm-1",
            "session_phase": DORMANT_PHASE,
            "clinical_checklist": checklist,
            "messages": [
                HumanMessage(content="My back is killing me"),
                AIMessage(content="Please go to the emergency department."),
            ],
        },
    )
    out = graph.invoke(
        {"session_id": "dorm-1", "messages": [HumanMessage(content="?")]},
        config,
    )
    assert out["final_response"] == DORMANT_REPLY
    assert out["session_phase"] == DORMANT_PHASE
    labels = {row["label"] for row in out["clinical_checklist"]}
    assert "age" in labels
    assert "sex" in labels


def test_dormant_yes_reenters_reasoning():
    graph = build_chat_graph()
    config = {"configurable": {"thread_id": "dorm-2"}}
    checklist = [
        {"text": "60", "kind": "demographic", "source": "pattern", "label": "age"},
        {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        {"text": "back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
    ]
    graph.update_state(
        config,
        {
            "session_id": "dorm-2",
            "session_phase": DORMANT_PHASE,
            "clinical_checklist": checklist,
            "comorbidities_acknowledged": True,
            "messages": [
                HumanMessage(content="My back is killing me"),
                AIMessage(content=DORMANT_REPLY),
            ],
        },
    )
    out = graph.invoke(
        {"session_id": "dorm-2", "messages": [HumanMessage(content="yes")]},
        config,
    )
    assert out["final_response"] != DORMANT_REPLY
    labels = {row["label"] for row in out["clinical_checklist"]}
    assert "age" in labels
    assert "sex" in labels


def test_merge_does_not_wipe_checklist_or_extraction_history():
    existing = {
        "session_id": "s1",
        "clinical_checklist": [
            {"text": "60", "kind": "demographic", "source": "pattern", "label": "age"},
        ],
        "extraction_history": [
            {"turn_index": 1, "user_message": "back pain"},
            {"turn_index": 8, "user_message": "ice"},
        ],
    }
    merged = merge_session_fields(
        existing,
        {
            "clinical_checklist": [],
            "extraction_history": [{"turn_index": 1, "user_message": "?"}],
        },
    )
    assert merged["clinical_checklist"][0]["text"] == "60"
    assert len(merged["extraction_history"]) == 3
    assert merged["extraction_history"][-1]["user_message"] == "?"
    assert merged["extraction_history"][1]["user_message"] == "ice"


def test_empty_checkpointer_resumes_dormant_from_session_json():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.orchestrator.dormant import DORMANT_REPLY as REPLY

    sid = "admin_resume"
    save_session(
        sid,
        clinical_checklist=[
            {"text": "60", "kind": "demographic", "source": "pattern", "label": "age"},
            {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        ],
        session_phase=DORMANT_PHASE,
        messages=[
            {"role": "user", "content": "My back is killing me"},
            {"role": "assistant", "content": "Please go to the emergency department."},
        ],
        extraction_history=[{"turn_index": 8, "user_message": "ice"}],
        orchestrator={
            "turn_index": 8,
            "question_mode": False,
            "questions_asked": 7,
            "coverage_ready": True,
            "session_phase": DORMANT_PHASE,
        },
    )
    client = TestClient(app)
    resp = client.post("/api/v1/chat", json={"session_id": sid, "message": "?"})
    assert resp.status_code == 200
    assert resp.json()["response"] == REPLY
    stored = load_session(sid)
    assert stored is not None
    assert any(row.get("text") == "60" for row in stored["clinical_checklist"])
    assert stored["session_phase"] == DORMANT_PHASE


_CHECKLIST = [
    {"text": "60", "kind": "demographic", "source": "pattern", "label": "age"},
    {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
    {"text": "back pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
]


def test_canned_dormant_hides_seeded_graph_and_skips_disposition_append():
    graph = build_chat_graph()
    config = {"configurable": {"thread_id": "dorm-graph-1"}}
    graph.update_state(
        config,
        {
            "session_id": "dorm-graph-1",
            "session_phase": DORMANT_PHASE,
            "clinical_checklist": _CHECKLIST,
            "graph_traversal": {"trace_id": "keep-disp"},
            "intake_traversal": {"trace_id": "keep-in"},
            "matched_factors": ["Recent trauma"],
            "candidate_conditions": ["Fracture"],
            "traversed_chunk_ids": ["c1"],
            "factor_matching_audit": {"summary": {}},
            "messages": [
                HumanMessage(content="My back is killing me"),
                AIMessage(content="Please go to the emergency department."),
            ],
        },
    )
    out = graph.invoke(
        {"session_id": "dorm-graph-1", "messages": [HumanMessage(content="?")]},
        config,
    )
    assert out["final_response"] == DORMANT_REPLY
    assert out.get("canned_dormant") is True
    assert exposed_chat_graph_fields(out) == (None, None)
    assert build_disposition_record(out, turn_index=2) is None

    existing = {
        "session_id": "dorm-graph-1",
        "orchestrator_history": [
            {
                "turn_index": 1,
                "question_mode": False,
                "session_phase": DORMANT_PHASE,
                "coverage_ready": True,
            }
        ],
        "disposition_history": [
            {"turn_index": 1, "final_response": "Please go to the emergency department."}
        ],
    }
    turn_index = user_message_count(transcript_from_messages(out["messages"]))
    assert turn_index == 2
    merged = merge_session_fields(
        existing,
        {
            "orchestrator": build_orchestrator_snapshot(out, turn_index=turn_index),
            "disposition": build_disposition_record(out, turn_index=turn_index),
        },
    )
    assert len(merged["disposition_history"]) == 1
    assert len(merged["orchestrator_history"]) == 2
    assert merged["orchestrator_history"][0]["coverage_ready"] is True


def test_generator_failure_stays_in_intake_and_retries():
    import app.orchestrator.graph as graph_mod
    import app.orchestrator.nodes as nodes
    from app.services.generator import GENERATOR_SYSTEM_FAILURE_TEXT

    def _stub_plan(state):
        state["question_mode"] = False
        return state

    with (
        patch.object(nodes, "plan_question_node", _stub_plan),
        patch.object(graph_mod, "plan_question_node", _stub_plan),
        patch(
            "app.services.generator.generate_response_result",
            return_value=(GENERATOR_SYSTEM_FAILURE_TEXT, "empty"),
        ),
        patch(
            "app.services.rag.chunk_retrieval.retrieve_rag_chunk_matches",
            return_value=[],
        ),
    ):
        graph = graph_mod.build_chat_graph()
        config = {"configurable": {"thread_id": "gen-fail-1"}}
        first = graph.invoke(
            {
                "session_id": "gen-fail-1",
                "messages": [HumanMessage(content="low back pain for a week")],
            },
            config,
        )
        assert (first.get("session_phase") or INTAKE_PHASE) == INTAKE_PHASE
        assert first["escalated"] is False
        assert first["generator_failed"] is True
        assert first["final_response"] == GENERATOR_SYSTEM_FAILURE_TEXT

        second = graph.invoke(
            {
                "session_id": "gen-fail-1",
                "messages": [HumanMessage(content="ok try again")],
            },
            config,
        )
        assert second["final_response"] != DORMANT_REPLY
        assert (second.get("session_phase") or INTAKE_PHASE) == INTAKE_PHASE


def test_risk_turn_after_question_keeps_prior_orchestrator_row():
    graph = build_chat_graph()
    config = {"configurable": {"thread_id": "risk-idx-1"}}
    graph.update_state(
        config,
        {
            "session_id": "risk-idx-1",
            "session_phase": INTAKE_PHASE,
            "clinical_checklist": _CHECKLIST,
            "extraction_history": [{"turn_index": 1, "user_message": "back pain"}],
            "messages": [
                HumanMessage(content="back pain"),
                AIMessage(content="How old are you?"),
            ],
            "questions_asked": 1,
        },
    )
    out = graph.invoke(
        {
            "session_id": "risk-idx-1",
            "messages": [HumanMessage(content="I have chest pain and cannot breathe.")],
        },
        config,
    )
    assert out["escalated"] is True
    turn_index = user_message_count(transcript_from_messages(out["messages"]))
    assert turn_index == 2
    existing = {
        "session_id": "risk-idx-1",
        "orchestrator_history": [
            {"turn_index": 1, "question_mode": True, "question_reason": "template_fallback:age"}
        ],
        "disposition_history": [],
    }
    merged = merge_session_fields(
        existing,
        {
            "orchestrator": build_orchestrator_snapshot(out, turn_index=turn_index),
            "disposition": build_disposition_record(out, turn_index=turn_index),
        },
    )
    assert len(merged["orchestrator_history"]) == 2
    assert merged["orchestrator_history"][0]["question_mode"] is True
    assert merged["orchestrator_history"][1]["escalated"] is True


def test_resume_values_restore_asked_factor_and_park_slot():
    patch = resume_values_from_session(
        {
            "session_id": "s-resume-factor",
            "clinical_checklist": _CHECKLIST,
            "session_phase": INTAKE_PHASE,
            "orchestrator": {
                "asked_factor": "Saddle anaesthesia",
                "slot_being_asked": "palliative",
                "questions_asked": 3,
            },
            "messages": [
                {"role": "user", "content": "back pain"},
                {"role": "assistant", "content": "Any numbness in the saddle area?"},
            ],
        }
    )
    assert patch["asked_factor"] == "Saddle anaesthesia"
    assert patch["last_asked_slot"] is None


def test_resume_asked_factor_credits_bare_no():
    graph = build_chat_graph()
    config = {"configurable": {"thread_id": "resume-factor-1"}}
    patch = resume_values_from_session(
        {
            "session_id": "s-resume-factor",
            "clinical_checklist": _CHECKLIST,
            "session_phase": INTAKE_PHASE,
            "orchestrator": {
                "asked_factor": "Saddle anaesthesia",
                "slot_being_asked": None,
                "questions_asked": 3,
            },
            "factor_states": {},
            "messages": [
                {"role": "user", "content": "back pain"},
                {"role": "assistant", "content": "Any numbness in the saddle area?"},
            ],
        }
    )
    graph.update_state(config, patch)
    out = graph.invoke(
        {"session_id": "s-resume-factor", "messages": [HumanMessage(content="no")]},
        config,
    )
    assert (out.get("factor_states") or {}).get("Saddle anaesthesia") == "denied"


def test_resume_does_not_infer_dormant_from_generator_failure_stub():
    patch = resume_values_from_session(
        {
            "session_id": "s-fail-resume",
            "clinical_checklist": _CHECKLIST,
            "disposition_history": [
                {
                    "turn_index": 3,
                    "safety_reason": "system_failure:generator_unavailable",
                    "final_response": "I'm temporarily unable to generate a recommendation",
                    "escalated": False,
                }
            ],
        }
    )
    assert patch["session_phase"] == INTAKE_PHASE
