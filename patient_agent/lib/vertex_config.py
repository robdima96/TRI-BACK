"""Vertex settings shared with TRI-BACK's generator (same env + ADC).

Resolution order for the model id (first non-empty wins):

1. CLI ``--model``
2. ``PATIENT_VERTEX_MODEL`` (patient-agent overlay; switch models without
   changing the TRI-BACK generator)
3. ``TRI_BACK_GENERATOR_MODEL``
4. ``gemini-2.5-flash`` (TRI-BACK default)

Auth is Application Default Credentials, same as ``bot/app/services/vertex_auth.py``.
Project / region come from ``TRI_BACK_VERTEX_PROJECT_ID`` and
``TRI_BACK_VERTEX_LOCATION`` (loaded from ``bot/.env`` if present).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VERTEX_MODEL = "gemini-2.5-flash"
DEFAULT_VERTEX_LOCATION = "us-central1"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATIENT_ROOT = Path(__file__).resolve().parents[1]
_ENV_LOADED = False


def _env_lookup(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def load_tri_back_env() -> None:
    """Load ``bot/.env`` then ``patient_agent/.env`` (overlay). Safe if files are missing."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        _ENV_LOADED = True
        return
    load_dotenv(_REPO_ROOT / "bot" / ".env")
    load_dotenv(_PATIENT_ROOT / ".env")
    _ENV_LOADED = True


@dataclass(frozen=True)
class VertexRuntime:
    project_id: str
    location: str
    model: str
    model_source: str


def resolve_vertex_model(cli_model: str | None = None) -> tuple[str, str]:
    """Return ``(model_id, source_label)``."""
    load_tri_back_env()
    if cli_model and cli_model.strip():
        return cli_model.strip(), "cli --model"
    patient = (os.environ.get("PATIENT_VERTEX_MODEL") or "").strip()
    if patient:
        return patient, "PATIENT_VERTEX_MODEL"
    generator = _env_lookup("TRI_BACK_GENERATOR_MODEL")
    if generator:
        source = (
            "TRI_BACK_GENERATOR_MODEL"
            if (os.environ.get("TRI_BACK_GENERATOR_MODEL") or "").strip()
            else "TRI_BACK_GENERATOR_MODEL"
        )
        return generator, source
    return DEFAULT_VERTEX_MODEL, "default"


def vertex_runtime(cli_model: str | None = None) -> VertexRuntime:
    load_tri_back_env()
    project = _env_lookup("TRI_BACK_VERTEX_PROJECT_ID")
    location = _env_lookup("TRI_BACK_VERTEX_LOCATION") or DEFAULT_VERTEX_LOCATION
    model, source = resolve_vertex_model(cli_model)
    if not project:
        raise RuntimeError(
            "TRI_BACK_VERTEX_PROJECT_ID is not set. It should come from bot/.env "
            "(same file TRI-BACK's generator uses). Optional overlay: patient_agent/.env"
        )
    return VertexRuntime(
        project_id=project,
        location=location,
        model=model,
        model_source=source,
    )
