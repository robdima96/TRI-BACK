"""Helpers for deduplicating encoder entities (checklist / logging).

Production RAG embeds the **full normalized user message**, not per-entity phrases.
Entity phrase builders remain for offline benchmarks (e.g.
``Embeddings test/compare_embedding_models_entities.py``).
"""

from __future__ import annotations

from app.schemas import EncoderEntity


def dedupe_encoder_entities(entities: list[EncoderEntity]) -> list[EncoderEntity]:
    """Keep first occurrence of each distinct entity ``text`` (case-insensitive)."""
    seen: set[str] = set()
    out: list[EncoderEntity] = []
    for ent in entities:
        key = ent.text.casefold().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(ent)
    return out


def entity_retrieval_phrase(entity: EncoderEntity) -> str:
    """Short phrase for embedding one entity (text + clinical label when useful)."""
    text = entity.text.strip()
    if not text:
        return ""
    label = (entity.label or "").strip()
    if not label:
        return text
    return f"{text} ({label})"


def build_retrieval_query_text(entities: list[EncoderEntity]) -> str:
    """Single string joining all deduped entity phrases (for logging / combined embed)."""
    phrases = [
        entity_retrieval_phrase(e)
        for e in dedupe_encoder_entities(entities)
        if entity_retrieval_phrase(e)
    ]
    return "; ".join(phrases)


def entity_retrieval_phrases(entities: list[EncoderEntity]) -> list[str]:
    """One deduped embedding phrase per entity (preferred for Chroma query)."""
    return [
        p
        for e in dedupe_encoder_entities(entities)
        if (p := entity_retrieval_phrase(e))
    ]
