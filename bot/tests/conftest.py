"""Isolate test env before ``app`` imports (Chroma path; no real model dirs)."""

from pathlib import Path
import os

import pytest


def _force_env(suffix: str, value: str) -> None:
    os.environ[f"TRI_BACK_{suffix}"] = value


def _pop_env(suffix: str) -> None:
    os.environ.pop(f"TRI_BACK_{suffix}", None)


os.environ.setdefault("TRI_BACK_CHROMA_PATH", ".chroma_pytest")

# Force both prefixes so a developer .env cannot disable retrieval under pytest.
_force_env("RAG", "1")
_force_env("LOAD_RAG", "1")

# Prevent pytest from probing real Windows model paths if .env overrides.
_force_env("ENCODER_DIR", "__pytest_no_encoder__")
_force_env("GLINER_MODEL_DIR", "__pytest_no_gliner__")

_force_env("LOAD_NER", "0")
_force_env("LOAD_GLINER", "0")
_force_env("LOAD_QUERY_CLASSIFIER", "0")
_force_env("LOAD_SAT_SPLITTER", "0")
_force_env("QUERY_CLASSIFIER_DIR", "__pytest_no_qc__")
_force_env("SAT_SPLITTER_DIR", "__pytest_no_sat__")

_force_env("GENERATOR_DIR", "__pytest_no_generator__")
_force_env("GENERATOR_BACKEND", "local")
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

# Deterministic disposition in unit tests unless a test opts into agentic.
os.environ.setdefault("TRI_BACK_DISPOSITION_MODE", "deterministic")

# Deterministic factor matching unless a test opts into the LLM cross-check.
_force_env("LLM_FACTOR_MATCH", "0")

# Public-host API key must not break local chat route tests.
_pop_env("BOT_API_KEY")
_force_env("ALLOW_OPEN_API", "1")
_pop_env("FORCE_FACTOR_ASK")


@pytest.fixture(autouse=True)
def clear_bot_api_key_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: open local API. Auth tests override ``settings.bot_api_key``."""
    from app.config import settings

    monkeypatch.setattr(settings, "bot_api_key", None)
    monkeypatch.setattr(settings, "allow_open_api", True)


@pytest.fixture(autouse=True)
def clear_force_factor_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "force_factor_ask", None)


@pytest.fixture(autouse=True)
def isolate_session_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid writing session JSON files into the repo during tests."""
    from app.config import settings

    monkeypatch.setattr(settings, "session_store_dir", str(tmp_path / "sessions"))


@pytest.fixture(autouse=True)
def isolate_langgraph_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test SQLite checkpointer and a fresh compiled graph on ``app.main``."""
    from app.config import settings
    from app.orchestrator import checkpointing
    from app.orchestrator.graph import build_chat_graph

    monkeypatch.setattr(
        settings,
        "checkpoint_sqlite_path",
        str(tmp_path / "langgraph_checkpoint.sqlite"),
    )
    monkeypatch.setattr(checkpointing, "_conn", None)
    monkeypatch.setattr(checkpointing, "_saver", None)

    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "chat_graph",
        build_chat_graph(checkpointer=checkpointing.get_checkpointer()),
    )