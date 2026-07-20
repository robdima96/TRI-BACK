"""Config and path checks for dual-backend RAG embeddings."""

from __future__ import annotations

from pathlib import Path

from app.config import (
    DEFAULT_GLINER_MODEL_DIR,
    DEFAULT_RAG_EMBEDDING_MODEL_DIR,
    settings,
)
from app.services.rag.embeddings import (
    rag_embedding_backend,
    rag_embedding_model_configured,
    unload_embedding_models,
)


def test_default_constants_separate_gliner_and_rag() -> None:
    assert DEFAULT_GLINER_MODEL_DIR != DEFAULT_RAG_EMBEDDING_MODEL_DIR


def test_default_rag_backend_is_sentence_transformers() -> None:
    assert rag_embedding_backend() == "sentence_transformers"


def test_rag_not_configured_for_pytest_stub_encoder_dir() -> None:
    unload_embedding_models()
    assert settings.encoder_model_dir == "__pytest_no_encoder__"
    assert rag_embedding_model_configured() is False


def test_sentence_transformer_path_detection(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    unload_embedding_models()
    from app.services.rag import embeddings as emb

    original = settings.encoder_model_dir
    try:
        settings.encoder_model_dir = str(tmp_path)
        assert emb._sentence_transformer_path_looks_valid(str(tmp_path))
        assert rag_embedding_model_configured()
    finally:
        settings.encoder_model_dir = original
        unload_embedding_models()
