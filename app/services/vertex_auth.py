"""Vertex AI authentication via user Application Default Credentials (no key file)."""

from __future__ import annotations

import os
from pathlib import Path

_ADC_WIN = Path(os.environ.get("APPDATA", "")) / "gcloud" / "application_default_credentials.json"
_ADC_UNIX = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"


def _adc_file_path() -> Path | None:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    if _ADC_WIN.is_file():
        return _ADC_WIN
    if _ADC_UNIX.is_file():
        return _ADC_UNIX
    return None


def vertex_adc_status() -> tuple[bool, str]:
    """
    Return whether Vertex can use Application Default Credentials.

    Prefers user ADC from ``gcloud auth application-default login``.
    Warns when ``GOOGLE_APPLICATION_CREDENTIALS`` points at a service account key.
    """
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if key_path:
        return (
            False,
            "GOOGLE_APPLICATION_CREDENTIALS is set — unset it for user ADC "
            f"({key_path})",
        )

    adc_path = _adc_file_path()
    if adc_path is None:
        return (
            False,
            "no Application Default Credentials — run: "
            "gcloud auth application-default login",
        )

    try:
        import google.auth
    except ImportError:
        return (
            False,
            "google-auth not installed; pip install -e '.[generator-api]'",
        )

    try:
        credentials, default_project = google.auth.default()
    except Exception as exc:
        return False, f"ADC load failed: {type(exc).__name__}: {exc}"

    cred_type = type(credentials).__name__
    detail = f"user ADC via {adc_path} (credentials={cred_type}"
    if default_project:
        detail += f", quota_project={default_project}"
    detail += ")"
    return True, detail
