"""Graph node tests for checklist enrichment."""

from unittest.mock import patch

from app.orchestrator.nodes import enrich_checklist_node, evaluate_coverage_node, plan_question_node
from app.services.intake_enricher import IntakeEnrichmentResult
from app.schemas import ChecklistItem


def test_enrich_checklist_node_merges_llm_rows():
    state = {
        "session_id": "sess-enrich-1",
        "message": "Yes",
        "message_normalized": "Yes",
        "turn_start_checklist": [
            {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
        ],
        "clinical_checklist": [
            {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
            {"text": "shooting", "kind": "symptom_quality", "source": "pattern", "label": "symptom_quality"},
        ],
        "encoder_turn_items": [
            {"text": "shooting", "kind": "symptom_quality", "source": "pattern", "label": "symptom_quality"},
        ],
        "extraction_history": [],
        "messages": [],
        "last_asked_slot": "symptom_anchor",
        "comorbidities_acknowledged": False,
    }
    enrichment = IntakeEnrichmentResult(
        status="applied",
        summary_reason="Confirmed chief complaint.",
        applied=[
            ChecklistItem(
                text="low back pain",
                kind="ner_entity",
                source="llm",
                label="symptom",
            )
        ],
        resulting_checklist=[
            {"text": "70", "kind": "demographic", "source": "pattern", "label": "age"},
            {
                "text": "shooting",
                "kind": "symptom_quality",
                "source": "pattern",
                "label": "symptom_quality",
            },
            {
                "text": "low back pain",
                "kind": "ner_entity",
                "source": "llm",
                "label": "symptom",
            },
        ],
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ):
        out = enrich_checklist_node(state)

    assert len(out["clinical_checklist"]) == 3
    assert out["clinical_checklist"][-1]["source"] == "llm"
    assert len(out["extraction_history"]) == 1
    record = out["extraction_history"][0]
    assert record["llm_enrichment"]["status"] == "applied"
    assert record["llm_enrichment"]["summary_reason"] == "Confirmed chief complaint."
    assert record["by_source"]["llm"][0]["text"] == "low back pain"
    assert any(item["source"] == "llm" for item in record["new_items"])


def test_enrich_checklist_node_applies_modify_and_delete():
    state = {
        "session_id": "sess-enrich-2",
        "message": "Not knee — low back. Rest does not help.",
        "message_normalized": "Not knee — low back. Rest does not help.",
        "turn_start_checklist": [
            {"text": "knee pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
            {"text": "rest", "kind": "palliative", "source": "pattern", "label": "palliative"},
        ],
        "clinical_checklist": [
            {"text": "knee pain", "kind": "ner_entity", "source": "gliner", "label": "symptom"},
            {"text": "rest", "kind": "palliative", "source": "pattern", "label": "palliative"},
        ],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "last_asked_slot": None,
        "comorbidities_acknowledged": False,
    }
    enrichment = IntakeEnrichmentResult(
        status="applied",
        summary_reason="Corrected symptom; removed false palliative.",
        modified=[
            {
                "id": "cl_sx",
                "before": {
                    "id": "cl_sx",
                    "text": "knee pain",
                    "kind": "ner_entity",
                    "source": "gliner",
                    "label": "symptom",
                    "confirmed": False,
                },
                "after": {
                    "id": "cl_sx",
                    "text": "low back pain",
                    "kind": "ner_entity",
                    "source": "llm",
                    "label": "symptom",
                    "confirmed": True,
                },
                "reason": "Patient corrected region.",
            }
        ],
        deleted=[
            {
                "id": "cl_pal",
                "before": {
                    "id": "cl_pal",
                    "text": "rest",
                    "kind": "palliative",
                    "source": "pattern",
                    "label": "palliative",
                    "confirmed": False,
                },
                "reason": "Patient denied rest helps.",
            }
        ],
        resulting_checklist=[
            {
                "id": "cl_sx",
                "text": "low back pain",
                "kind": "ner_entity",
                "source": "llm",
                "label": "symptom",
                "confirmed": True,
            }
        ],
    )
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=enrichment,
    ):
        out = enrich_checklist_node(state)

    assert out["clinical_checklist"] == enrichment.resulting_checklist
    log = out["extraction_history"][0]["llm_enrichment"]
    assert len(log["modified"]) == 1
    assert len(log["deleted"]) == 1
    assert out["extraction_history"][0]["by_source"]["llm"][0]["text"] == "low back pain"


def test_enrich_credits_i_dont_know_on_comorbidities_without_llm_ack():
    """Public Vertex often leaves comorbidities open; slot credit must close it."""
    state = {
        "session_id": "sess-comorbid-idk",
        "message": "i dont know",
        "message_normalized": "i dont know",
        "turn_start_checklist": [
            {"text": "30", "kind": "demographic", "source": "pattern", "label": "age"},
            {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        ],
        "clinical_checklist": [
            {"text": "30", "kind": "demographic", "source": "pattern", "label": "age"},
            {"text": "male", "kind": "demographic", "source": "pattern", "label": "sex"},
        ],
        "encoder_turn_items": [],
        "extraction_history": [],
        "messages": [],
        "last_asked_slot": "comorbidities",
        "asked_factor": None,
        "comorbidities_acknowledged": False,
    }
    with patch(
        "app.orchestrator.nodes.propose_checklist_enrichment",
        return_value=IntakeEnrichmentResult(
            status="no_changes",
            summary_reason="Patient does not know; no checklist change.",
        ),
    ):
        out = enrich_checklist_node(state)

    comorb = [r for r in out["clinical_checklist"] if r.get("kind") == "comorbidity"]
    assert len(comorb) == 1
    assert comorb[0]["text"] == "N/A"

    covered = evaluate_coverage_node(out)
    assert covered["comorbidities_acknowledged"] is True
    planned = plan_question_node(covered)
    assert planned.get("slot_being_asked") != "comorbidities"
