"""Password hashing utilities."""



from __future__ import annotations



import bcrypt



_admin_hash_cache: tuple[str, str] | None = None





def hash_password(password: str) -> str:

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")





def verify_password(password: str, password_hash: str) -> bool:

    try:

        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    except ValueError:

        return False





def admin_password_hash() -> str:

    """Bcrypt hash of the current admin plaintext (cached per plaintext value)."""

    global _admin_hash_cache

    from tri_back_study_app.auth.config import admin_password_plaintext



    plaintext = admin_password_plaintext()

    if _admin_hash_cache and _admin_hash_cache[0] == plaintext:

        return _admin_hash_cache[1]

    hashed = hash_password(plaintext)

    _admin_hash_cache = (plaintext, hashed)

    return hashed



def verify_admin_password(password: str) -> bool:

    """Match env password via bcrypt, or local fallbacks ``triback`` / ``digimsk``."""

    from tri_back_study_app.auth.config import (

        ADMIN_PASSWORD_FALLBACK,

        ADMIN_PASSWORD_FALLBACK_LEGACY,

        admin_password_plaintext,

    )

    from tri_back_study_app.config import PUBLIC_ACCESS, env_lookup



    env_pw = (env_lookup("TRI_BACK_ADMIN_PASSWORD") or "").strip()

    if env_pw:

        return verify_password(password, admin_password_hash())

    if PUBLIC_ACCESS:

        return False

    _ = admin_password_plaintext()  # raises if public (already handled)

    return (password or "") in (ADMIN_PASSWORD_FALLBACK, ADMIN_PASSWORD_FALLBACK_LEGACY)


