"""Post-disposition dormant phase and durable session resume."""

from langchain_core.messages import AIMessage, HumanMessage

from app.orchestrator.dormant import (
    DORMANT_PHASE,
    DORMANT_REPLY,
    detect_symptom_change,
)
from app.orchestrator.graph import build_chat_graph
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
