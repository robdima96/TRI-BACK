"""LLM checklist enrichment (Option A intake): add / modify / delete."""

from __future__ import annotations

import json
from unittest.mock import patch

from app.orchestrator.coverage import evaluate_checklist_coverage
from app.services.intake_enricher import (
    ChecklistOperation,
    _extract_json_object,
    _validate_proposed_row,
    apply_checklist_operations,
    propose_checklist_enrichment,
)


def test_extract_json_object_from_fence():
    raw = '```json\n{"summary_reason": "ok", "checklist_operations": []}\n```'
    data = _extract_json_object(raw)
    assert data is not None
    assert data["summary_reason"] == "ok"


def test_validate_proposed_row_accepts_symptom():
    row = _validate_proposed_row(
        {
            "text": "low back pain",
            "kind": "ner_entity",
            "label": "symptom",
            "reason": "Patient confirmed chief complaint.",
        }
    )
    assert row is not None
    assert row.text == "low back pain"


def test_validate_proposed_row_rejects_unknown_kind():
    assert (
        _validate_proposed_row(
            {"text": "foo", "kind": "medication", "label": "x", "reason": "nope"}
        )
        is None
    )


def test_apply_modify_and_delete_with_stable_ids():
    checklist = [
        {"id": "cl_age", "text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
        {
            "id": "cl_sx",
            "text": "knee pain",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "symptom",
        },
        {
            "id": "cl_pal",
            "text": "ibuprofen",
            "kind": "palliative",
            "source": "pattern",
            "label": "palliative",
        },
    ]
    ops = [
        ChecklistOperation(
            op="modify",
            id="cl_sx",
            text="low back pain",
            kind="ner_entity",
            label="symptom",
            reason="Patient corrected the body region.",
        ),
        ChecklistOperation(
            op="delete",
            id="cl_pal",
            reason="Patient said medication was not for this pain.",
        ),
        ChecklistOperation(
            op="add",
            text="3 months",
            kind="duration",
            label="duration",
            reason="Stated duration.",
        ),
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist, ops
    )
    assert not rejected
    assert len(deleted) == 1
    assert deleted[0]["before"]["text"] == "ibuprofen"
    assert deleted[0]["id"] == "cl_pal"
    assert len(modified) == 1
    assert modified[0]["after"]["text"] == "low back pain"
    assert modified[0]["after"]["id"] == "cl_sx"
    assert modified[0]["after"]["confirmed"] is True
    assert [r["text"] for r in resulting] == ["70", "low back pain", "3 months"]
    assert len(applied) == 1
    assert applied[0].text == "3 months"
    assert applied[0].confirmed is True
    assert applied[0].id
    assert resulting[1]["id"] == "cl_sx"


def test_apply_canonicalizes_empty_palliative_add_to_na():
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        [],
        [
            ChecklistOperation(
                op="add",
                text="I don't know",
                kind="palliative",
                label="palliative",
                reason="Patient could not name a relieving factor.",
            )
        ],
    )
    assert not rejected and not modified and not deleted
    assert len(applied) == 1
    assert applied[0].text == "N/A"
    assert applied[0].kind == "palliative"
    assert resulting[0]["text"] == "N/A"


def test_apply_keeps_na_when_llm_modifies_to_nothing():
    checklist = [
        {
            "id": "cl_pal",
            "text": "N/A",
            "kind": "palliative",
            "source": "slot_answer",
            "label": "palliative",
        }
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist,
        [
            ChecklistOperation(
                op="modify",
                id="cl_pal",
                text="nothing",
                kind="palliative",
                label="palliative",
                reason="Patient said nothing helps.",
            )
        ],
    )
    assert not applied and not deleted
    assert resulting[0]["text"] == "N/A"
    assert resulting[0]["kind"] == "palliative"
    assert resulting[0]["id"] == "cl_pal"


def test_apply_rejects_delete_of_na_slot_row():
    checklist = [
        {
            "id": "cl_pal",
            "text": "N/A",
            "kind": "palliative",
            "source": "slot_answer",
            "label": "palliative",
        }
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist,
        [ChecklistOperation(op="delete", id="cl_pal", reason="Uncertain row.")],
    )
    assert resulting[0]["text"] == "N/A"
    assert not deleted and not applied and not modified
    assert rejected and rejected[0]["reject_reason"] == "na_slot_protected"


def test_apply_rejects_unknown_id_and_duplicate_add():
    checklist = [
        {"id": "cl_age", "text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
    ]
    ops = [
        ChecklistOperation(op="delete", id="cl_missing", reason="bad id"),
        ChecklistOperation(
            op="add",
            text="70",
            kind="demographic",
            label="age",
            reason="dup",
        ),
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist, ops
    )
    assert resulting[0]["text"] == "70"
    assert resulting[0]["id"] == "cl_age"
    assert not applied and not modified and not deleted
    assert {r["reject_reason"] for r in rejected} == {
        "unknown_id",
        "duplicate_of_existing_checklist_row",
    }


def test_delete_wins_over_modify_on_same_id():
    checklist = [
        {
            "id": "cl_q",
            "text": "sharp",
            "kind": "symptom_quality",
            "source": "pattern",
            "label": "symptom_quality",
        },
    ]
    ops = [
        ChecklistOperation(
            op="modify",
            id="cl_q",
            text="dull",
            kind="symptom_quality",
            label="symptom_quality",
            reason="correction",
        ),
        ChecklistOperation(op="delete", id="cl_q", reason="retracted"),
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist, ops
    )
    assert resulting == []
    assert deleted and not modified and not applied
    assert not rejected  # modify cleared when delete arrives after


def test_apply_rejects_kind_family_mismatch_on_confirmed_row():
    checklist = [
        {
            "id": "cl_trauma",
            "text": "fell from a ladder",
            "kind": "provocative",
            "source": "llm",
            "label": "provocative",
            "confirmed": True,
        },
    ]
    ops = [
        ChecklistOperation(
            op="modify",
            id="cl_trauma",
            text="aspirin",
            kind="comorbidity",
            label="comorbidity",
            reason="Patient takes aspirin.",
        ),
        ChecklistOperation(
            op="add",
            text="aspirin",
            kind="comorbidity",
            label="comorbidity",
            reason="Patient takes aspirin.",
        ),
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist, ops
    )
    assert not modified and not deleted
    assert any(r["reject_reason"] == "kind_family_mismatch" for r in rejected)
    assert resulting[0]["text"] == "fell from a ladder"
    assert resulting[0]["id"] == "cl_trauma"
    assert len(applied) == 1
    assert applied[0].text == "aspirin"
    assert applied[0].confirmed is True


def test_apply_allows_cross_family_modify_when_unconfirmed():
    checklist = [
        {
            "id": "cl_x",
            "text": "chair",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "body part",
            "confirmed": False,
        },
    ]
    ops = [
        ChecklistOperation(
            op="modify",
            id="cl_x",
            text="sitting",
            kind="provocative",
            label="provocative",
            reason="Mislabelled extractor row.",
        ),
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist, ops
    )
    assert not rejected
    assert modified[0]["after"]["kind"] == "provocative"
    assert resulting[0]["confirmed"] is True
    assert resulting[0]["id"] == "cl_x"


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_uses_slim_single_message_prompt(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "No changes.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [],
            "next_intake": None,
        }
    )
    history = [
        {"role": "user", "content": "Low back pain for 3 weeks"},
        {"role": "assistant", "content": "How severe is the pain on a 0-10 scale?"},
        {"role": "user", "content": "About 7"},
        {"role": "assistant", "content": "What makes it worse?"},
    ]
    propose_checklist_enrichment(
        checklist=[{"text": "low back pain", "kind": "ner_entity", "label": "symptom"}],
        conversation_history=history,
        latest_user_message="Sitting makes it worse",
        last_asked_slot="provocative",
    )
    mock_gen.assert_called_once()
    messages = mock_gen.call_args[0][0]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert "Last exchange (assistant question + latest patient reply):" in content
    assert "assistant: What makes it worse?" in content
    assert "user: Sitting makes it worse" in content
    assert "Low back pain for 3 weeks" not in content
    assert "If severity is 7+ or described as severe, do not choose provocative" in content
    assert mock_gen.call_args.kwargs.get("max_new_tokens") == 4096
    assert mock_gen.call_args.kwargs.get("response_mime_type") == "application/json"
    assert mock_gen.call_args.kwargs.get("response_schema") is not None


@patch("app.services.intake_enricher.generator_model_configured", return_value=False)
def test_enrichment_skipped_when_generator_unavailable(mock_cfg):
    result = propose_checklist_enrichment(
        checklist=[],
        conversation_history=[],
        latest_user_message="yes",
    )
    assert result.status == "unavailable"
    assert not result.applied_items


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_applies_symptom_from_confirmation(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Patient affirmed low back pain as chief complaint.",
            "comorbidities_acknowledged": False,
            "checklist_additions": [
                {
                    "text": "low back pain",
                    "kind": "ner_entity",
                    "label": "symptom",
                    "reason": "Confirmed after intake question.",
                }
            ],
        }
    )
    checklist = [
        {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
        {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        {"text": "shooting", "kind": "symptom_quality", "source": "pattern", "label": "symptom_quality"},
    ]
    result = propose_checklist_enrichment(
        checklist=checklist,
        conversation_history=[
            {"role": "user", "content": "Low back pain, shooting pain to my leg"},
            {"role": "assistant", "content": "Is low back pain your main concern today?"},
        ],
        latest_user_message="Yes, it's really painful",
        last_asked_slot="symptom_anchor",
        session_id="admin_test",
        turn_index=3,
    )
    assert result.status == "applied"
    assert len(result.applied) == 1
    assert result.applied[0].source == "llm"
    assert result.applied[0].label == "symptom"
    assert result.applied[0].confirmed is True
    assert result.resulting_checklist is not None
    assert result.resulting_checklist[-1]["text"] == "low back pain"
    assert result.resulting_checklist[-1]["confirmed"] is True
    assert all(r.get("id") for r in result.resulting_checklist)

    merged = result.resulting_checklist
    coverage, _, _ = evaluate_checklist_coverage(
        checklist=merged,
        comorbidities_acknowledged=True,
    )
    assert len(coverage["symptom_instances"]) == 1
    assert "symptom_anchor" not in {m["slot"] for m in coverage["missing_slots"]}


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_asked_factor_reply_is_parsed(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Patient is on steroids.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [],
            "asked_factor_reply": "affirmed",
            "next_intake": None,
        }
    )
    result = propose_checklist_enrichment(
        checklist=[],
        latest_user_message="I take prednisone daily",
        last_asked_factor="Corticosteroids",
    )
    assert result.asked_factor_reply == "affirmed"
    prompt = mock_gen.call_args[0][0][0]["content"]
    assert "asked_factor_reply" in prompt


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_patient_answer_is_parsed_from_packet(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Recorded severe pain.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [],
            "asked_factor_reply": "not_answered",
            "patient_answer": (
                "Severe pain is on this graph; I am not giving a triage recommendation."
            ),
            "next_intake": None,
        }
    )
    result = propose_checklist_enrichment(
        checklist=[],
        latest_user_message="my pain is severe",
        question_spans=["is my back pain dangerous?"],
        graph_packet="Current graph factor: Severe pain\n- Diabetes — a diagnosis of diabetes",
    )
    assert "severe pain" in (result.patient_answer or "").casefold()
    prompt = mock_gen.call_args[0][0][0]["content"]
    assert "patient_answer" in prompt
    assert "is my back pain dangerous?" in prompt
    assert "Diabetes" in prompt


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_dedupes_existing_rows(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "No new facts.",
            "checklist_additions": [
                {
                    "text": "70",
                    "kind": "demographic",
                    "label": "age",
                    "reason": "Already known.",
                }
            ],
        }
    )
    checklist = [
        {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
    ]
    result = propose_checklist_enrichment(
        checklist=checklist,
        conversation_history=[],
        latest_user_message="yes",
    )
    assert result.status == "rejected_all"
    assert not result.applied
    assert len(result.rejected) == 1
    assert result.resulting_checklist is None


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_operations_modify_and_delete(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Corrected symptom and removed retracted palliative.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [
                {
                    "op": "modify",
                    "id": "cl_sx",
                    "text": "low back pain",
                    "kind": "ner_entity",
                    "label": "symptom",
                    "reason": "Patient clarified region.",
                },
                {
                    "op": "delete",
                    "id": "cl_pal",
                    "reason": "Patient said rest does not help.",
                },
            ],
        }
    )
    checklist = [
        {
            "id": "cl_sx",
            "text": "knee pain",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "symptom",
        },
        {
            "id": "cl_pal",
            "text": "rest",
            "kind": "palliative",
            "source": "pattern",
            "label": "palliative",
        },
    ]
    result = propose_checklist_enrichment(
        checklist=checklist,
        conversation_history=[
            {"role": "user", "content": "Actually it is low back pain, rest makes it worse"},
        ],
        latest_user_message="Actually it is low back pain, rest makes it worse",
    )
    assert result.status == "applied"
    assert len(result.modified) == 1
    assert len(result.deleted) == 1
    assert result.resulting_checklist == [
        {
            "id": "cl_sx",
            "text": "low back pain",
            "kind": "ner_entity",
            "source": "llm",
            "label": "symptom",
            "confirmed": True,
        }
    ]


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_index_ops_are_invalid(mock_cfg, mock_gen):
    """Index-addressed ops must not apply (no deprecated fallback)."""
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Tried indexes.",
            "checklist_operations": [
                {
                    "op": "modify",
                    "index": 1,
                    "text": "aspirin",
                    "kind": "comorbidity",
                    "label": "comorbidity",
                    "reason": "med",
                },
                {"op": "delete", "index": 1, "reason": "gone"},
            ],
        }
    )
    checklist = [
        {
            "id": "cl_trauma",
            "text": "fell from a ladder",
            "kind": "provocative",
            "source": "llm",
            "label": "provocative",
            "confirmed": True,
        },
    ]
    result = propose_checklist_enrichment(
        checklist=checklist,
        conversation_history=[],
        latest_user_message="I take aspirin",
    )
    assert not result.proposed
    assert result.status == "no_changes"
    assert result.resulting_checklist is None


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_rejects_invalid_operation_kind(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Bad row.",
            "checklist_operations": [
                {
                    "op": "add",
                    "text": "aspirin",
                    "kind": "medication",
                    "label": "med",
                    "reason": "invented",
                }
            ],
        }
    )
    result = propose_checklist_enrichment(
        checklist=[],
        conversation_history=[],
        latest_user_message="I take aspirin",
    )
    assert result.status == "no_changes"
    assert not result.proposed
    assert result.resulting_checklist is None


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_enrichment_rejects_string_false_comorbidities_ack(mock_cfg, mock_gen):
    """Only JSON boolean true may set comorbidities_acknowledged."""
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Patient said none.",
            "comorbidities_acknowledged": "false",
            "checklist_operations": [],
            "next_intake": None,
        }
    )
    result = propose_checklist_enrichment(
        checklist=[],
        conversation_history=[],
        latest_user_message="none",
        last_asked_slot="comorbidities",
    )
    assert result.comorbidities_acknowledged is False


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_consistency_guard_clears_next_slot_when_skipping_gap(mock_cfg, mock_gen):
    """Sitting-bug pattern: LLM jumps to palliative without adding provocative."""
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Patient provided a provocative factor.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [
                {
                    "op": "delete",
                    "id": "cl_chair",
                    "reason": "chair is not a body part.",
                },
            ],
            "next_intake": {
                "slot": "palliative",
                "question": "Does anything make the pain feel better?",
            },
        }
    )
    checklist = [
        {"id": "cl_age", "text": "30", "kind": "demographic", "source": "slot_answer", "label": "age"},
        {"id": "cl_sex", "text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        {
            "id": "cl_sx",
            "text": "dull ache",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "symptom",
        },
        {
            "id": "cl_q",
            "text": "dull",
            "kind": "symptom_quality",
            "source": "pattern",
            "label": "symptom_quality",
        },
        {
            "id": "cl_sev",
            "text": "5",
            "kind": "severity",
            "source": "pattern",
            "label": "symptom_severity",
        },
        {
            "id": "cl_dur",
            "text": "3 weeks",
            "kind": "duration",
            "source": "pattern",
            "label": "duration",
        },
        {
            "id": "cl_chair",
            "text": "chair",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "body part",
        },
    ]
    result = propose_checklist_enrichment(
        checklist=checklist,
        conversation_history=[],
        latest_user_message=(
            "It's a dull ache, but it's been going on for 3 weeks now "
            "and it's hard to sit in my chair at work"
        ),
        last_asked_slot="symptom_quality",
        comorbidities_acknowledged=True,
    )
    assert result.consistency_warning is not None
    assert result.consistency_warning["proposed_next_slot"] == "palliative"
    assert result.consistency_warning["authoritative_next_slot"] == "provocative"
    assert result.next_slot is None
    assert result.next_question is None
    assert "consistency_warning" in result.to_log_dict()


@patch("app.services.intake_enricher.generate_from_messages")
@patch("app.services.intake_enricher.generator_model_configured", return_value=True)
def test_consistency_guard_keeps_matching_next_slot(mock_cfg, mock_gen):
    mock_gen.return_value = json.dumps(
        {
            "summary_reason": "Added sitting as provocative.",
            "comorbidities_acknowledged": False,
            "checklist_operations": [
                {
                    "op": "add",
                    "text": "sitting",
                    "kind": "provocative",
                    "label": "provocative",
                    "reason": "Hard to sit at work.",
                },
            ],
            "next_intake": {
                "slot": "palliative",
                "question": "What helps your dull ache feel better?",
            },
        }
    )
    checklist = [
        {"text": "30", "kind": "demographic", "source": "slot_answer", "label": "age"},
        {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        {
            "text": "dull ache",
            "kind": "ner_entity",
            "source": "gliner",
            "label": "symptom",
        },
        {
            "text": "dull",
            "kind": "symptom_quality",
            "source": "pattern",
            "label": "symptom_quality",
        },
        {
            "text": "5",
            "kind": "severity",
            "source": "pattern",
            "label": "symptom_severity",
        },
        {
            "text": "3 weeks",
            "kind": "duration",
            "source": "pattern",
            "label": "duration",
        },
    ]
    result = propose_checklist_enrichment(
        checklist=checklist,
        conversation_history=[],
        latest_user_message="hard to sit in my chair at work",
        last_asked_slot="symptom_quality",
        comorbidities_acknowledged=True,
    )
    assert result.consistency_warning is None
    assert result.next_slot == "palliative"
    assert result.next_question
    assert any(item.text == "sitting" for item in result.applied)
