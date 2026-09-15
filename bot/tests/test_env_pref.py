"""TRI_BACK_* env vars prefer over legacy DIGIMSK_* aliases."""

from __future__ import annotations

import pytest

from app.config import _env_bool, env_lookup


def test_env_lookup_prefers_tri_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRI_BACK_RAG", "0")
    monkeypatch.setenv("DIGIMSK_RAG", "1")
    assert env_lookup("TRI_BACK_RAG") == "0"
    assert _env_bool("TRI_BACK_RAG", True) is False


def test_env_lookup_falls_back_to_digimsk(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TRI_BACK_RAG", raising=False)
    monkeypatch.setenv("DIGIMSK_RAG", "0")
    assert env_lookup("TRI_BACK_RAG") == "0"
    assert _env_bool("TRI_BACK_RAG", True) is False


def test_env_lookup_unset_uses_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TRI_BACK_CHAT_RATE_LIMIT", raising=False)
    monkeypatch.delenv("DIGIMSK_CHAT_RATE_LIMIT", raising=False)
    assert env_lookup("TRI_BACK_CHAT_RATE_LIMIT") is None
    assert _env_bool("TRI_BACK_PUBLIC_ACCESS", False) is False


def test_legacy_load_rag_alias(monkeypatch: pytest.MonkeyPatch):
    """TRI_BACK_RAG / DIGIMSK_RAG win; else TRI_BACK_LOAD_RAG / DIGIMSK_LOAD_RAG."""
    for key in (
        "TRI_BACK_RAG",
        "DIGIMSK_RAG",
        "TRI_BACK_LOAD_RAG",
        "DIGIMSK_LOAD_RAG",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DIGIMSK_LOAD_RAG", "0")
    assert _env_bool("TRI_BACK_RAG", _env_bool("TRI_BACK_LOAD_RAG", True)) is False
    monkeypatch.setenv("TRI_BACK_RAG", "1")
    assert _env_bool("TRI_BACK_RAG", _env_bool("TRI_BACK_LOAD_RAG", True)) is True
