"""RAG disabled via ``settings.rag_load`` mirrors ``DIGIMSK_LOAD_RAG`` env."""

from app.config import settings
from app.services.rag import retrieve_evidence


def test_retrieve_evidence_empty_when_rag_load_false(monkeypatch):
    monkeypatch.setattr(settings, "rag_load", False)
    out = retrieve_evidence("some normalized query", [0.1] * settings.encoder_embedding_dim)
    assert out == []


def test_retrieve_evidence_empty_when_empty_query(monkeypatch):
    monkeypatch.setattr(settings, "rag_load", True)
    out = retrieve_evidence("", [0.1] * settings.encoder_embedding_dim)
    assert out == []


def test_retrieve_evidence_empty_when_no_embedding_and_compute_fails(monkeypatch):
    import app.services.rag as rag_mod

    monkeypatch.setattr(settings, "rag_load", True)

    def fake_compute(_text: str) -> list[float]:
        return []

    monkeypatch.setattr(rag_mod, "compute_query_embedding", fake_compute)
    out = retrieve_evidence("low back pain", None)
    assert out == []


def test_retrieve_evidence_full_query_embedding(monkeypatch):
    import app.services.rag as rag_mod
    from app.schemas import ChunkMatch

    monkeypatch.setattr(settings, "rag_load", True)
    dim = settings.encoder_embedding_dim
    embedded: list[str] = []

    def fake_compute(text: str) -> list[float]:
        embedded.append(text)
        return [0.1] * dim

    def fake_chunks(
        query: str,
        query_embedding: list[float] | None = None,
        *,
        top_k: int | None = None,
        sub_collections: list[str] | None = None,
    ) -> list[ChunkMatch]:
        if query_embedding is None:
            fake_compute(query)
        return [
            ChunkMatch(
                chunk_id="chunk-1",
                source="src",
                snippet=embedded[-1] if embedded else query,
                score=0.9,
                sub_collection="red_flags",
            )
        ]

    monkeypatch.setattr(rag_mod, "retrieve_chunk_matches", fake_chunks)

    out = retrieve_evidence("low back pain for 3 weeks", None)
    assert embedded == ["low back pain for 3 weeks"]
    assert len(out) == 1
    assert out[0].snippet == "low back pain for 3 weeks"
    assert out[0].chunk_id == "chunk-1"


def test_retrieve_evidence_uses_prefilled_embedding(monkeypatch):
    import app.services.rag as rag_mod
    from app.schemas import ChunkMatch

    monkeypatch.setattr(settings, "rag_load", True)
    dim = settings.encoder_embedding_dim
    vec = [0.2] * dim

    def fake_chunks(
        query: str,
        query_embedding: list[float] | None = None,
        *,
        top_k: int | None = None,
        sub_collections: list[str] | None = None,
    ) -> list[ChunkMatch]:
        assert query_embedding == vec
        return [
            ChunkMatch(
                chunk_id="c1",
                source="s",
                snippet="hit",
                score=0.5,
                sub_collection="red_flags",
            )
        ]

    monkeypatch.setattr(rag_mod, "retrieve_chunk_matches", fake_chunks)

    out = retrieve_evidence("ignored when embedding passed", vec)
    assert len(out) == 1
    assert out[0].chunk_id == "c1"
