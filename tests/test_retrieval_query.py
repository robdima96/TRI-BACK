"""Entity-only RAG query building."""

from app.schemas import EncoderEntity
from app.services.rag.retrieval_query import (
    build_retrieval_query_text,
    dedupe_encoder_entities,
    entity_retrieval_phrase,
    entity_retrieval_phrases,
)


def test_dedupe_encoder_entities_case_insensitive():
    entities = [
        EncoderEntity(text="Pain", label="symptom"),
        EncoderEntity(text="pain", label="symptom"),
        EncoderEntity(text="  Pain  ", label="symptom"),
        EncoderEntity(text="diabetes", label="comorbidity"),
    ]
    out = dedupe_encoder_entities(entities)
    assert [e.text for e in out] == ["Pain", "diabetes"]


def test_entity_retrieval_phrase_includes_label():
    assert entity_retrieval_phrase(
        EncoderEntity(text="low back", label="body part")
    ) == "low back (body part)"
    assert entity_retrieval_phrase(EncoderEntity(text="male", label="")) == "male"


def test_build_retrieval_query_text_joins_deduped_phrases():
    entities = [
        EncoderEntity(text="pain", label="symptom"),
        EncoderEntity(text="pain", label="symptom"),
        EncoderEntity(text="diabetes", label="comorbidity"),
    ]
    assert build_retrieval_query_text(entities) == "pain (symptom); diabetes (comorbidity)"
    assert entity_retrieval_phrases(entities) == [
        "pain (symptom)",
        "diabetes (comorbidity)",
    ]
