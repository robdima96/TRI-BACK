"""Authentication configuration."""



from __future__ import annotations



import os



ADMIN_USERNAME = "admin"

ADMIN_STUDY_ID = "admin"  # written to logs as study_id for admin sessions



# Local-only fallback when DIGIMSK_ADMIN_PASSWORD is unset and public mode is off.

# Never rely on this for a public share link — set DIGIMSK_ADMIN_PASSWORD instead.

ADMIN_PASSWORD_FALLBACK = "digimsk"





def admin_password_plaintext() -> str:

    """Admin password from env, or local fallback when not in public mode."""

    from digimsk_study_app.config import PUBLIC_ACCESS



    env_pw = (os.getenv("DIGIMSK_ADMIN_PASSWORD") or "").strip()

    if env_pw:

        return env_pw

    if PUBLIC_ACCESS:

        raise RuntimeError(

            "DIGIMSK_PUBLIC_ACCESS=1 requires DIGIMSK_ADMIN_PASSWORD "

            "(do not use the local fallback on a public link)."

        )

    return ADMIN_PASSWORD_FALLBACK


