"""Persistent session snapshots as JSON files (one file per session id)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings

_log = logging.getLogger(__name__)

_MAX_STORED_MESSAGES = 40  # cap transcript size (user + assistant turns)


# maps session id to safe and consistent file path
def _session_file_path(session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    root = Path(settings.session_store_dir)
    return root / f"sess_{digest}.json"

# return decoded JSON or None if missing/invalid
def load_session(session_id: str) -> dict[str, Any] | None:
    if not session_id or not session_id.strip():
        return None
    path = _session_file_path(session_id.strip())
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("session load failed %s: %s", path, e)
        return None


def save_session(
    session_id: str,
    *,
    clinical_checklist: list[dict[str, Any]],
    messages: list[dict[str, str]],
) -> None:
    """Persist merged checklist and trimmed transcript."""
    if not session_id or not session_id.strip():
        return
    sid = session_id.strip()
    path = _session_file_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = messages[-_MAX_STORED_MESSAGES:]
    payload = {
        "session_id": sid,
        "clinical_checklist": clinical_checklist,
        "messages": trimmed,
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(path)
