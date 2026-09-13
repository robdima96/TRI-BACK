"""Vertex settings shared with DigiMSKbot's generator (same env + ADC).

Resolution order for the model id (first non-empty wins):

1. CLI ``--model``
2. ``PATIENT_VERTEX_MODEL`` (patient-agent overlay; switch models without
   changing the DigiMSK generator)
3. ``DIGIMSK_GENERATOR_MODEL`` (same as the bot generator)
4. ``gemini-2.5-flash`` (DigiMSK default)

Auth is Application Default Credentials, same as ``bot/app/services/vertex_auth.py``.
Project / region come from ``DIGIMSK_VERTEX_PROJECT_ID`` and
``DIGIMSK_VERTEX_LOCATION`` (loaded from ``bot/.env`` if present).
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


def load_digimsk_env() -> None:
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
    load_digimsk_env()
    if cli_model and cli_model.strip():
        return cli_model.strip(), "cli --model"
    patient = (os.environ.get("PATIENT_VERTEX_MODEL") or "").strip()
    if patient:
        return patient, "PATIENT_VERTEX_MODEL"
    generator = (os.environ.get("DIGIMSK_GENERATOR_MODEL") or "").strip()
    if generator:
        return generator, "DIGIMSK_GENERATOR_MODEL"
    return DEFAULT_VERTEX_MODEL, "default"


def vertex_runtime(cli_model: str | None = None) -> VertexRuntime:
    load_digimsk_env()
    project = (os.environ.get("DIGIMSK_VERTEX_PROJECT_ID") or "").strip()
    location = (
        (os.environ.get("DIGIMSK_VERTEX_LOCATION") or "").strip()
        or DEFAULT_VERTEX_LOCATION
    )
    model, source = resolve_vertex_model(cli_model)
    if not project:
        raise RuntimeError(
            "DIGIMSK_VERTEX_PROJECT_ID is not set. It should come from bot/.env "
            "(same file DigiMSKbot's generator uses). Optional overlay: patient_agent/.env"
        )
    return VertexRuntime(
        project_id=project,
        location=location,
        model=model,
        model_source=source,
    )
