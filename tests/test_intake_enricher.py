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


def test_apply_modify_and_delete_with_stable_indexes():
    checklist = [
        {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
        {"text": "knee pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
        {"text": "ibuprofen", "kind": "palliative", "source": "pattern", "label": "palliative"},
    ]
    ops = [
        ChecklistOperation(
            op="modify",
            index=2,
            text="low back pain",
            kind="ner_entity",
            label="symptom",
            reason="Patient corrected the body region.",
        ),
        ChecklistOperation(
            op="delete",
            index=3,
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
    assert len(modified) == 1
    assert modified[0]["after"]["text"] == "low back pain"
    assert [r["text"] for r in resulting] == ["70", "low back pain", "3 months"]
    assert len(applied) == 1
    assert applied[0].text == "3 months"


def test_apply_rejects_out_of_range_and_duplicate_add():
    checklist = [
        {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
    ]
    ops = [
        ChecklistOperation(op="delete", index=9, reason="bad index"),
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
    assert resulting == checklist
    assert not applied and not modified and not deleted
    assert {r["reject_reason"] for r in rejected} == {
        "index_out_of_range",
        "duplicate_of_existing_checklist_row",
    }


def test_delete_wins_over_modify_on_same_index():
    checklist = [
        {"text": "sharp", "kind": "symptom_quality", "source": "pattern", "label": "symptom_quality"},
    ]
    ops = [
        ChecklistOperation(
            op="modify",
            index=1,
            text="dull",
            kind="symptom_quality",
            label="symptom_quality",
            reason="correction",
        ),
        ChecklistOperation(op="delete", index=1, reason="retracted"),
    ]
    resulting, applied, modified, deleted, rejected = apply_checklist_operations(
        checklist, ops
    )
    assert resulting == []
    assert deleted and not modified and not applied
    assert not rejected  # modify cleared when delete arrives after


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
    assert result.resulting_checklist is not None
    assert result.resulting_checklist[-1]["text"] == "low back pain"

    merged = result.resulting_checklist
    coverage, _, _ = evaluate_checklist_coverage(
        checklist=merged,
        comorbidities_acknowledged=True,
    )
    assert len(coverage["symptom_instances"]) == 1
    assert "symptom_anchor" not in {m["slot"] for m in coverage["missing_slots"]}


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
                    "index": 1,
                    "text": "low back pain",
                    "kind": "ner_entity",
                    "label": "symptom",
                    "reason": "Patient clarified region.",
                },
                {
                    "op": "delete",
                    "index": 2,
                    "reason": "Patient said rest does not help.",
                },
            ],
        }
    )
    checklist = [
        {"text": "knee pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
        {"text": "rest", "kind": "palliative", "source": "pattern", "label": "palliative"},
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
            "text": "low back pain",
            "kind": "ner_entity",
            "source": "llm",
            "label": "symptom",
        }
    ]


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
