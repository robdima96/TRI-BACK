"""Deterministic human-readable session IDs."""

from __future__ import annotations


def allocate_session_id(study_id: str, role: str, login_count: int) -> str:
    """
    Participants: {study_id}_{n}
    Admin: admin_{n}
    """
    n = max(1, int(login_count))
    if role == "admin":
        return f"admin_{n}"
    return f"{study_id}_{n}"
