"""Isolate test env before ``app`` imports (Chroma path; no real model dirs)."""

from pathlib import Path
import os

import pytest


os.environ.setdefault("DIGIMSK_CHROMA_PATH", ".chroma_pytest")

# Prefer DIGIMSK_RAG over the legacy DIGIMSK_LOAD_RAG alias; force both so a
# developer .env with DIGIMSK_RAG=0 cannot disable retrieval under pytest.
os.environ["DIGIMSK_RAG"] = "1"
os.environ["DIGIMSK_LOAD_RAG"] = "1"

# Prevent pytest from probing real Windows model paths if .env overrides.
os.environ["DIGIMSK_ENCODER_DIR"] = "__pytest_no_encoder__"
os.environ["DIGIMSK_GLINER_MODEL_DIR"] = "__pytest_no_gliner__"

os.environ["DIGIMSK_LOAD_NER"] = "0"
os.environ["DIGIMSK_LOAD_GLINER"] = "0"

os.environ["DIGIMSK_GENERATOR_DIR"] = "__pytest_no_generator__"
os.environ["DIGIMSK_GENERATOR_BACKEND"] = "local"
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

# Deterministic disposition in unit tests unless a test opts into agentic.
os.environ.setdefault("DIGIMSK_DISPOSITION_MODE", "deterministic")

# Deterministic factor matching unless a test opts into the LLM cross-check.
os.environ["DIGIMSK_LLM_FACTOR_MATCH"] = "0"

# Public-host API key must not break local chat route tests.
os.environ.pop("DIGIMSK_BOT_API_KEY", None)


@pytest.fixture(autouse=True)
def clear_bot_api_key_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default: no Bearer required. Auth tests override ``settings.bot_api_key``."""
    from app.config import settings

    monkeypatch.setattr(settings, "bot_api_key", None)


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