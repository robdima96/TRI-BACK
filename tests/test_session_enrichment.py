"""Session enrichment helpers."""

from app.orchestrator.checklist import merge_checklist_items
from app.schemas import ChecklistItem
from app.session_enrichment import (
    build_turn_extraction_record,
    default_engagement,
    engagement_from_messages,
    split_checklist_by_source,
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


def test_turn_extraction_record_tracks_deduped_checklist():
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
    assert len(record["clinical_checklist"]) == 2


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
