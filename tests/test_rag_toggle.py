"""RAG disabled via ``settings.rag_load`` mirrors ``DIGIMSK_LOAD_RAG`` env."""

from app.config import settings
from app.services.rag import retrieve_evidence


def test_retrieve_evidence_empty_when_rag_load_false(monkeypatch):
    monkeypatch.setattr(settings, "rag_load", False)
    out = retrieve_evidence("some normalized query", [0.1] * settings.encoder_embedding_dim)
    assert out == []


def test_retrieve_evidence_empty_when_no_query_embedding(monkeypatch):
    monkeypatch.setattr(settings, "rag_load", True)
    out = retrieve_evidence("some normalized query", [])
    assert out == []
