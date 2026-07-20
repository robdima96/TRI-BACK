"""NER checklist deduplication by span text."""

from app.schemas import ChecklistItem
from app.services.encoder import _dedupe_checklist_items_by_text


def test_dedupe_ner_items_case_insensitive_text():
    items = [
        ChecklistItem(text="low back", kind="ner_entity", source="ner", label="body part"),
        ChecklistItem(text="Low back", kind="ner_entity", source="ner", label="anatomy"),
        ChecklistItem(text="pain", kind="ner_entity", source="ner", label="symptom"),
    ]
    out = _dedupe_checklist_items_by_text(items)
    assert len(out) == 2
    assert out[0].text == "low back"
    assert out[0].label == "body part"
    assert out[1].text == "pain"


def test_dedupe_ner_items_preserves_first_occurrence_order():
    items = [
        ChecklistItem(text="bruising", kind="ner_entity", source="ner", label="sign"),
        ChecklistItem(text="fall", kind="ner_entity", source="ner", label="injury"),
        ChecklistItem(text="bruising", kind="ner_entity", source="ner", label="symptom"),
    ]
    out = _dedupe_checklist_items_by_text(items)
    assert [it.text for it in out] == ["bruising", "fall"]
    assert out[0].label == "sign"
