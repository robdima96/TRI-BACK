"""Authentication configuration."""

from __future__ import annotations

ADMIN_USERNAME = "admin"

ADMIN_STUDY_ID = "admin"  # written to logs as study_id for admin sessions

# Local-only fallbacks when TRI_BACK_ADMIN_PASSWORD is unset and public mode is off.
# Never rely on these for a public share link — set TRI_BACK_ADMIN_PASSWORD instead.
# ``digimsk`` remains accepted locally until sunset.
ADMIN_PASSWORD_FALLBACK = "triback"
ADMIN_PASSWORD_FALLBACK_LEGACY = "digimsk"


def admin_password_plaintext() -> str:
    """Admin password from env, or local fallback when not in public mode."""
    from tri_back_study_app.config import PUBLIC_ACCESS, env_lookup

    env_pw = (env_lookup("TRI_BACK_ADMIN_PASSWORD") or "").strip()
    if env_pw:
        return env_pw
    if PUBLIC_ACCESS:
        raise RuntimeError(
            "TRI_BACK_PUBLIC_ACCESS=1 requires TRI_BACK_ADMIN_PASSWORD "
            "(legacy DIGIMSK_ADMIN_PASSWORD still works; do not use the local fallback on a public link)."
        )
    return ADMIN_PASSWORD_FALLBACK
