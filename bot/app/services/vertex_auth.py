"""Vertex AI authentication via Application Default Credentials.

Locally: prefer user ADC from ``gcloud auth application-default login``.
On Cloud Run / GCE: metadata-server credentials from ``google.auth.default()``.
"""

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


def _on_cloud_run() -> bool:
    return bool(os.environ.get("K_SERVICE") or os.environ.get("CLOUD_RUN_JOB"))


def vertex_adc_status() -> tuple[bool, str]:
    """
    Return whether Vertex can use Application Default Credentials.

    Prefers user ADC from ``gcloud auth application-default login``.
    On Cloud Run, accepts the runtime service-account via the metadata server.
    Warns when ``GOOGLE_APPLICATION_CREDENTIALS`` points at a service account key
    (local misuse); that env is unusual on Cloud Run.
    """
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if key_path and not _on_cloud_run():
        return (
            False,
            "GOOGLE_APPLICATION_CREDENTIALS is set — unset it for user ADC "
            f"({key_path})",
        )

    try:
        import google.auth
    except ImportError:
        return (
            False,
            "google-auth not installed; pip install -e '.[generator-api]'",
        )

    adc_path = _adc_file_path() if not key_path else Path(key_path)

    try:
        credentials, default_project = google.auth.default()
    except Exception as exc:
        if adc_path is None and not _on_cloud_run():
            return (
                False,
                "no Application Default Credentials — run: "
                "gcloud auth application-default login",
            )
        return False, f"ADC load failed: {type(exc).__name__}: {exc}"

    cred_type = type(credentials).__name__
    if adc_path is not None and adc_path.is_file() and not key_path:
        detail = f"user ADC via {adc_path} (credentials={cred_type}"
    elif _on_cloud_run():
        detail = f"Cloud Run runtime SA (credentials={cred_type}"
    else:
        detail = f"ADC (credentials={cred_type}"
    if default_project:
        detail += f", quota_project={default_project}"
    detail += ")"
    return True, detail
