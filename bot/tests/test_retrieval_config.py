"""Retrieval path config validation."""

import pytest

from app.config import Settings, validate_retrieval_paths


def test_validate_requires_at_least_one_path(monkeypatch):
    from app import config as config_mod

    monkeypatch.setattr(
        config_mod,
        "settings",
        Settings(
            rag_load=False,
            graphrag_load=False,
        ),
    )
    with pytest.raises(ValueError, match="TRI_BACK_RAG"):
        validate_retrieval_paths()
