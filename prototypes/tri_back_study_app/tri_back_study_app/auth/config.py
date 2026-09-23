"""Authentication configuration."""

from __future__ import annotations

ADMIN_USERNAME = "admin"

ADMIN_STUDY_ID = "admin"  # written to logs as study_id for admin sessions


def admin_password_plaintext() -> str:
    """Admin password from TRI_BACK_ADMIN_PASSWORD. Required for all runs."""
    from tri_back_study_app.config import env_lookup

    env_pw = (env_lookup("TRI_BACK_ADMIN_PASSWORD") or "").strip()
    if env_pw:
        return env_pw
    raise RuntimeError(
        "TRI_BACK_ADMIN_PASSWORD is required in .env (local and hosted)."
    )
