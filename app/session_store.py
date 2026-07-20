"""Persistent session snapshots as JSON files (one file per session id)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.session_enrichment import default_session_fields, engagement_from_messages

_log = logging.getLogger(__name__)

_MAX_STORED_MESSAGES = 40  # cap transcript size (user + assistant turns)


def _session_file_path(session_id: str) -> Path:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    root = Path(settings.session_store_dir)
    return root / f"sess_{digest}.json"


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


def save_session(session_id: str, **fields: Any) -> None:
    """Persist harmonized session snapshot (checklist, extraction history, engagement)."""
    if not session_id or not session_id.strip():
        return
    sid = session_id.strip()
    fields.pop("session_id", None)
    path = _session_file_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_session(sid) or default_session_fields(sid)
    existing.update(fields)
    existing["session_id"] = sid
    trimmed = existing.get("messages") or []
    if isinstance(trimmed, list):
        existing["messages"] = trimmed[-_MAX_STORED_MESSAGES:]
    if "engagement" not in fields and existing.get("messages"):
        existing["engagement"] = engagement_from_messages(
            existing["messages"],
            existing=existing.get("engagement"),
        )
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
