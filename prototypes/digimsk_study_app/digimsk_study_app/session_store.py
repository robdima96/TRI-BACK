"""Study overlay on bot-owned session JSON under ``bot/data/sessions``.

Clinical / disposition logging is written by the chatbot API. This module only
adds study metadata, engagement timing, and feedback onto the same files.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from digimsk_study_app.config import MAX_STORED_MESSAGES, SESSIONS_DIR

_log = logging.getLogger(__name__)

_STUDY_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9]+_[0-9]+$")
_RESERVED_BASENAMES = frozenset({"test_log.json"})

# Fields owned by the bot pipeline — never clobber when patching study overlays.
_BOT_OWNED_KEYS = frozenset(
    {
        "clinical_checklist",
        "extraction_history",
        "orchestrator",
        "orchestrator_history",
        "disposition",
        "disposition_history",
        "matched_factors",
        "candidate_conditions",
        "traversed_chunk_ids",
        "factor_matching_audit",
        "agent_trace",
        "graph_traversal",
    }
)


def _session_file_path(session_id: str) -> Path:
    sid = session_id.strip()
    if _STUDY_SESSION_ID_RE.match(sid):
        return SESSIONS_DIR / f"{sid}.json"
    import hashlib

    digest = hashlib.sha256(sid.encode("utf-8")).hexdigest()
    return SESSIONS_DIR / f"sess_{digest}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _default_session(
    session_id: str,
    *,
    study_id: str,
    role: str,
    group_id: int,
    login_count: int,
    login_at: str,
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "session_id": session_id,
        "study_id": study_id,
        "role": role,
        "group_id": group_id,
        "login_count": login_count,
        "login_at": login_at,
        "started_at": now,
        "last_active_at": now,
        "time_on_task_sec": 0.0,
        "turn_count": 0,
        "messages": [],
        "engagement": {
            "turns": [],
            "total_user_words": 0,
            "total_user_chars": 0,
            "mean_round_trip_ms": 0.0,
            "median_round_trip_ms": 0.0,
            "session_duration_sec": 0.0,
            "feedback_up_count": 0,
            "feedback_down_count": 0,
        },
    }


def load_session(session_id: str) -> dict[str, Any] | None:
    if not session_id or not session_id.strip():
        return None
    path = _session_file_path(session_id.strip())
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        _log.warning("session load failed %s: %s", path, exc)
        return None


def init_session(
    session_id: str,
    *,
    study_id: str,
    role: str,
    group_id: int,
    login_count: int,
    login_at: str,
) -> dict[str, Any]:
    payload = _default_session(
        session_id,
        study_id=study_id,
        role=role,
        group_id=group_id,
        login_count=login_count,
        login_at=login_at,
    )
    fields = dict(payload)
    fields.pop("session_id", None)
    save_session(session_id, **fields)
    return payload


def save_session(session_id: str, /, **fields: Any) -> None:
    """Patch study overlay fields onto the bot session file (no bot-field wipes).

    ``session_id`` is positional-only so callers may safely ``save_session(sid, **loaded)``
    when ``loaded`` still contains a ``session_id`` key.
    """
    if not session_id or not session_id.strip():
        return
    sid = session_id.strip()
    fields.pop("session_id", None)
    # Drop any accidental bot-owned keys from study callers.
    for key in list(fields):
        if key in _BOT_OWNED_KEYS:
            fields.pop(key)
    path = _session_file_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_session(sid) or {"session_id": sid}
    existing.update(fields)
    existing["session_id"] = sid
    existing["last_active_at"] = _now_iso()
    trimmed = existing.get("messages") or []
    if isinstance(trimmed, list):
        existing["messages"] = trimmed[-MAX_STORED_MESSAGES:]
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_session_files() -> list[dict[str, Any]]:
    root = SESSIONS_DIR
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        if path.name in _RESERVED_BASENAMES:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("session_id"):
                out.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return out
