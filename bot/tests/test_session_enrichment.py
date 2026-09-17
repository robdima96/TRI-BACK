"""Session enrichment helpers."""

from app.orchestrator.checklist import merge_checklist_items
from app.schemas import ChecklistItem
from app.session_enrichment import (
    build_disposition_record,
    build_orchestrator_snapshot,
    build_turn_extraction_record,
    compact_graph_for_session,
    default_engagement,
    default_session_fields,
    engagement_from_messages,
    exposed_chat_graph_fields,
    slim_factor_matching_audit,
    split_checklist_by_source,
)
from app.session_store import (
    is_study_session_id,
    merge_messages_preserving_study,
    merge_session_fields,
    session_file_path,
)


def test_split_checklist_by_source():
    items = [
        ChecklistItem(text="70", kind="demographic", source="pattern", label="age"),
        ChecklistItem(text="pain", kind="symptom", source="gliner", label="symptom"),
    ]
    grouped = split_checklist_by_source(items)
    assert len(grouped["pattern"]) == 1
    assert len(grouped["gliner"]) == 1
    assert grouped["safety_phrase"] == []


def test_turn_extraction_record_tracks_new_items_without_full_checklist():
    prior = [
        {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
    ]
    current = [
        ChecklistItem(text="70", kind="demographic", source="pattern", label="age"),
        ChecklistItem(text="pain", kind="symptom", source="gliner", label="symptom"),
    ]
    merged = merge_checklist_items(prior, current)
    record = build_turn_extraction_record(
        turn_index=2,
        user_message="back pain",
        turn_items=current,
        prior_checklist=prior,
        merged_checklist=merged,
        timestamp="2026-07-03T12:00:00-07:00",
    )
    assert record["turn_index"] == 2
    assert len(record["by_source"]["gliner"]) == 1
    assert len(record["new_items"]) == 1
    assert record["new_items"][0]["text"] == "pain"
    assert "clinical_checklist" not in record


def test_turn_extraction_record_includes_llm_enrichment():
    prior: list[dict[str, str]] = []
    merged = [
        {
            "text": "low back pain",
            "kind": "ner_entity",
            "source": "llm",
            "label": "symptom",
        }
    ]
    record = build_turn_extraction_record(
        turn_index=1,
        user_message="yes",
        turn_items=[],
        prior_checklist=prior,
        merged_checklist=merged,
        llm_enrichment={
            "status": "applied",
            "summary_reason": "Confirmed chief complaint.",
            "applied": merged,
            "proposed": merged,
            "rejected": [],
            "comorbidities_acknowledged": False,
        },
    )
    assert record["llm_enrichment"]["summary_reason"] == "Confirmed chief complaint."
    assert record["by_source"]["llm"][0]["text"] == "low back pain"
    assert record["new_items"] == merged


def test_engagement_from_messages_counts_user_turns():
    messages = [
        {"role": "user", "content": "hello world"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "knee pain"},
    ]
    engagement = engagement_from_messages(messages, existing=default_engagement())
    assert len(engagement["turns"]) == 2
    assert engagement["total_user_words"] == 4


def test_study_session_filenames_are_literal(tmp_path):
    assert is_study_session_id("admin_15")
    assert is_study_session_id("user_55")
    assert is_study_session_id("425_1")
    assert not is_study_session_id("sess-multi-1")
    assert session_file_path("admin_15", root=tmp_path).name == "admin_15.json"
    assert session_file_path("ad-hoc", root=tmp_path).name.startswith("sess_")


def test_compact_graph_strips_duplicated_fields():
    compact = compact_graph_for_session(
        {
            "trace_id": "t1",
            "checklist_items": [{"text": "x"}],
            "matched_factors": ["Age over 50"],
            "candidate_conditions": ["Fracture"],
            "factor_matching": {"summary": {}},
            "agent_trace": {"status": "ok"},
            "steps": [{"title": "seed"}],
        }
    )
    assert compact is not None
    assert compact["trace_id"] == "t1"
    assert compact["steps"]
    assert "checklist_items" not in compact
    assert "matched_factors" not in compact
    assert "candidate_conditions" not in compact
    assert "factor_matching" not in compact
    assert "agent_trace" not in compact


def test_slim_factor_audit_drops_partitions():
    slim = slim_factor_matching_audit(
        {
            "summary": {"matched_count": 1},
            "items": [{"status": "matched"}],
            "gaps": [],
            "matched": [{"status": "matched"}],
            "unmatched": [],
        }
    )
    assert slim is not None
    assert "matched" not in slim
    assert "unmatched" not in slim
    assert slim["items"]


def test_orchestrator_snapshot_includes_safety_fields():
    snap = build_orchestrator_snapshot(
        {
            "risk_hits": ["cancer_history"],
            "escalated": True,
            "safety_reason": "risk_policy",
            "question_mode": False,
            "questions_asked": 2,
            "coverage": {"ready_for_disposition": True, "missing_slots": []},
            "generator_failed": False,
        },
        turn_index=3,
    )
    assert snap["risk_hits"] == ["cancer_history"]
    assert snap["escalated"] is True
    assert snap["safety_reason"] == "risk_policy"
    assert snap["coverage_ready"] is True
    assert snap["factor_states"] == {}


def test_orchestrator_snapshot_includes_factor_states():
    snap = build_orchestrator_snapshot(
        {
            "question_mode": True,
            "factor_states": {"Bladder dysfunction": "denied"},
        },
        turn_index=2,
    )
    assert snap["factor_states"] == {"Bladder dysfunction": "denied"}


def test_disposition_skipped_on_question_mode():
    assert (
        build_disposition_record(
            {"question_mode": True, "matched_factors": ["Age over 50"]},
            turn_index=1,
        )
        is None
    )


def test_merge_preserves_disposition_after_question_turn():
    existing = {
        "session_id": "s1",
        "disposition_history": [
            {
                "turn_index": 2,
                "matched_factors": ["Age over 50"],
                "candidate_conditions": ["Fracture"],
            }
        ],
        "matched_factors": ["Age over 50"],
        "candidate_conditions": ["Fracture"],
        "graph_traversal": {"trace_id": "keep-me"},
        "agent_trace": {"status": "ok"},
    }
    merged = merge_session_fields(
        existing,
        {
            "clinical_checklist": [{"text": "pain", "kind": "symptom", "source": "gliner", "label": ""}],
            "orchestrator": {
                "turn_index": 3,
                "question_mode": True,
                "escalated": False,
                "risk_hits": [],
                "safety_reason": None,
            },
            # Accidental empties from a question turn must not wipe.
            "matched_factors": [],
            "candidate_conditions": [],
            "graph_traversal": None,
            "agent_trace": None,
        },
    )
    assert merged["matched_factors"] == ["Age over 50"]
    assert merged["candidate_conditions"] == ["Fracture"]
    assert merged["graph_traversal"]["trace_id"] == "keep-me"
    assert merged["agent_trace"]["status"] == "ok"
    assert len(merged["disposition_history"]) == 1
    assert merged["orchestrator"]["question_mode"] is True
    assert len(merged["orchestrator_history"]) == 1


def test_merge_appends_disposition_history():
    existing = {
        "session_id": "s1",
        "disposition_history": [],
        "orchestrator_history": [],
    }
    merged = merge_session_fields(
        existing,
        {
            "disposition": {
                "turn_index": 4,
                "matched_factors": ["Diabetes"],
                "candidate_conditions": ["Infection"],
                "graph_traversal": {"trace_id": "d1"},
                "factor_matching_audit": {"summary": {}},
                "agent_trace": None,
                "traversed_chunk_ids": ["c1"],
            }
        },
    )
    assert len(merged["disposition_history"]) == 1
    assert merged["matched_factors"] == ["Diabetes"]
    assert merged["graph_traversal"]["trace_id"] == "d1"


def test_merge_appends_intake_history_and_preserves_on_disposition():
    existing = {
        "session_id": "s1",
        "intake_history": [],
        "orchestrator_history": [],
        "factor_states": {"Neuro sensory deficit": "affirmed"},
    }
    merged = merge_session_fields(
        existing,
        {
            "intake": {
                "turn_index": 2,
                "asked_factor": "Saddle anaesthesia",
                "question_reason": "rank:t1:CES:Saddle anaesthesia",
                "factor_states": {"Neuro sensory deficit": "affirmed"},
                "intake_traversal": {"trace_id": "in1", "mode": "intake_gap"},
            }
        },
    )
    assert len(merged["intake_history"]) == 1
    assert merged["intake_traversal"]["trace_id"] == "in1"

    later = merge_session_fields(
        merged,
        {
            "disposition": {
                "turn_index": 4,
                "matched_factors": ["Neuro sensory deficit"],
                "graph_traversal": {"trace_id": "d1"},
            },
            "intake_traversal": None,
        },
    )
    assert later["graph_traversal"]["trace_id"] == "d1"
    assert later["intake_traversal"]["trace_id"] == "in1"
    assert later["factor_states"]["Neuro sensory deficit"] == "affirmed"


def test_merge_disposition_replaces_intake_snapshot():
    existing = {
        "session_id": "s1",
        "intake_history": [
            {
                "turn_index": 2,
                "intake_traversal": {"trace_id": "in1", "mode": "intake_gap"},
            }
        ],
        "intake_traversal": {"trace_id": "in1", "mode": "intake_gap"},
        "disposition_history": [],
    }
    merged = merge_session_fields(
        existing,
        {
            "disposition": {
                "turn_index": 4,
                "matched_factors": ["Neuro sensory deficit"],
                "graph_traversal": {"trace_id": "d1"},
                "intake_traversal": {"trace_id": "final-path", "mode": "intake_gap"},
            }
        },
    )
    assert merged["graph_traversal"]["trace_id"] == "d1"
    assert merged["intake_traversal"]["trace_id"] == "final-path"
    assert merged["intake_history"][0]["intake_traversal"]["trace_id"] == "in1"


def test_exposed_chat_graph_fields_hidden_on_question_turns():
    graph, intake = exposed_chat_graph_fields(
        {
            "question_mode": True,
            "graph_traversal": {"trace_id": "g1"},
            "intake_traversal": {"trace_id": "in1"},
        }
    )
    assert graph is None
    assert intake is None


def test_exposed_chat_graph_fields_on_disposition():
    graph, intake = exposed_chat_graph_fields(
        {
            "question_mode": False,
            "graph_traversal": {"trace_id": "g1"},
            "intake_traversal": {"trace_id": "in1"},
        }
    )
    assert graph == {"trace_id": "g1"}
    assert intake == {"trace_id": "in1"}


def test_merge_messages_preserves_feedback_and_message_id():
    existing = [
        {"role": "user", "content": "hi", "message_id": "msg_000"},
        {
            "role": "assistant",
            "content": "How old are you?",
            "message_id": "msg_001",
            "feedback": {"rating": "up", "rated_at": "2026-08-05T12:00:00+00:00"},
        },
    ]
    incoming = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "How old are you?"},
        {"role": "user", "content": "50"},
        {"role": "assistant", "content": "What sex?"},
    ]
    merged = merge_messages_preserving_study(existing, incoming)
    assert merged[1]["feedback"]["rating"] == "up"
    assert merged[1]["message_id"] == "msg_001"
    assert merged[3]["content"] == "What sex?"


def test_merge_messages_keeps_study_intro_prefix_and_feedback():
    existing = [
        {
            "role": "assistant",
            "content": "Welcome to TRI-BACK.",
            "message_id": "msg_intro",
            "feedback": {"rating": "up", "rated_at": "t0"},
        },
        {"role": "user", "content": "low back pain", "message_id": "msg_000_u"},
        {
            "role": "assistant",
            "content": "How old are you?",
            "message_id": "msg_000",
            "feedback": {"rating": "down", "rated_at": "t1"},
        },
    ]
    # Bot LangGraph transcript has no canned intro.
    incoming = [
        {"role": "user", "content": "low back pain"},
        {"role": "assistant", "content": "How old are you?"},
    ]
    merged = merge_messages_preserving_study(existing, incoming)
    assert merged[0]["message_id"] == "msg_intro"
    assert merged[0]["feedback"]["rating"] == "up"
    assert merged[1]["content"] == "low back pain"
    assert merged[2]["feedback"]["rating"] == "down"
    assert merged[2]["message_id"] == "msg_000"


def test_merge_session_fields_keeps_feedback_when_bot_rewrites_messages():
    existing = {
        "session_id": "admin_1",
        "messages": [
            {"role": "user", "content": "hello", "message_id": "msg_000"},
            {
                "role": "assistant",
                "content": "How old are you?",
                "message_id": "msg_001",
                "feedback": {"rating": "down", "rated_at": "t0"},
            },
        ],
        "engagement": {"feedback_up_count": 0, "feedback_down_count": 1, "turns": []},
    }
    merged = merge_session_fields(
        existing,
        {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "How old are you?"},
                {"role": "user", "content": "50"},
                {"role": "assistant", "content": "Next?"},
            ],
        },
    )
    assert merged["messages"][1]["feedback"]["rating"] == "down"
    assert merged["messages"][1]["message_id"] == "msg_001"


def test_engagement_from_messages_counts_feedback_ratings():
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "a", "feedback": {"rating": "up"}},
        {"role": "user", "content": "more"},
        {"role": "assistant", "content": "b", "feedback": {"rating": "down"}},
    ]
    engagement = engagement_from_messages(messages, existing=default_engagement())
    assert engagement["feedback_up_count"] == 1
    assert engagement["feedback_down_count"] == 1


def test_default_session_fields_include_generator_provenance():
    from app.config import settings

    fields = default_session_fields("425_1")
    assert fields["generator_backend"] == settings.generator_backend
    assert fields["generator_model"] == settings.generator_model
    assert "generator_model" in fields
    assert "generator_backend" in fields
