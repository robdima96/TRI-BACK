"""Persistent session snapshots as JSON files (one file per session id).

Session logging is owned by the bot. Every chat inference path writes here
(``data/sessions``). Study-style ids (``admin_15``, ``user_55``, ``425_1``) use
human-readable filenames; other ids are hashed for privacy.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.session_enrichment import (
    DISPOSITION_SNAPSHOT_KEYS,
    default_session_fields,
    engagement_from_messages,
)

_log = logging.getLogger(__name__)

_MAX_STORED_MESSAGES = 40  # cap transcript size (user + assistant turns)

# Study / admin login ids: roleOrStudyId_loginCount (e.g. admin_15, user_55, 425_1).
_STUDY_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9]+_[0-9]+$")

# Reference / non-session files that must not be treated as live sessions.
_RESERVED_BASENAMES = frozenset({"test_log.json"})


def is_study_session_id(session_id: str) -> bool:
    """True when the id should be stored as ``{session_id}.json`` (not hashed)."""
    return bool(_STUDY_SESSION_ID_RE.match((session_id or "").strip()))


def session_file_path(session_id: str, *, root: Path | None = None) -> Path:
    """Resolve the on-disk path for a session id."""
    sid = (session_id or "").strip()
    base = root if root is not None else Path(settings.session_store_dir)
    if is_study_session_id(sid):
        return base / f"{sid}.json"
    digest = hashlib.sha256(sid.encode("utf-8")).hexdigest()
    return base / f"sess_{digest}.json"


def _session_file_path(session_id: str) -> Path:
    return session_file_path(session_id)


def load_session(session_id: str) -> dict[str, Any] | None:
    if not session_id or not session_id.strip():
        return None
    path = _session_file_path(session_id.strip())
    if not path.is_file():
        # Migration: study ids previously stored as hashed sess_*.json
        if is_study_session_id(session_id.strip()):
            legacy = Path(settings.session_store_dir) / (
                f"sess_{hashlib.sha256(session_id.strip().encode('utf-8')).hexdigest()}.json"
            )
            if legacy.is_file():
                path = legacy
            else:
                return None
        else:
            return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("session load failed %s: %s", path, e)
        return None


def _append_by_turn_index(
    history: list[dict[str, Any]] | None,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    """Append ``record``, or replace the last entry when turn_index matches."""
    out = list(history or [])
    turn_index = record.get("turn_index")
    if out and turn_index is not None and out[-1].get("turn_index") == turn_index:
        out[-1] = record
    else:
        out.append(record)
    return out


def merge_session_fields(existing: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Merge a turn update into the session snapshot without wiping disposition.

    - ``disposition`` / ``orchestrator`` records append to history lists.
    - Empty/None disposition snapshot fields from a question turn do not clear
      previously stored graph / factor / agent audits.
    """
    merged = dict(existing)
    incoming = dict(fields)

    disposition = incoming.pop("disposition", None)
    orchestrator = incoming.pop("orchestrator", None)

    # Never let callers null-out durable disposition snapshots.
    for key in DISPOSITION_SNAPSHOT_KEYS:
        if key not in incoming:
            continue
        value = incoming[key]
        if value is None or value == []:
            if merged.get(key) not in (None, [], {}):
                incoming.pop(key)

    merged.update(incoming)

    if orchestrator and isinstance(orchestrator, dict):
        merged["orchestrator"] = orchestrator
        merged["orchestrator_history"] = _append_by_turn_index(
            merged.get("orchestrator_history"),
            orchestrator,
        )

    if disposition and isinstance(disposition, dict):
        merged["disposition_history"] = _append_by_turn_index(
            merged.get("disposition_history"),
            disposition,
        )
        # Latest disposition convenience mirrors (single source in history + tip).
        for key in DISPOSITION_SNAPSHOT_KEYS:
            if key in disposition:
                merged[key] = disposition[key]

    return merged


def save_session(session_id: str, **fields: Any) -> None:
    """Persist harmonized session snapshot (checklist, histories, disposition)."""
    if not session_id or not session_id.strip():
        return
    sid = session_id.strip()
    fields.pop("session_id", None)
    path = _session_file_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_session(sid) or default_session_fields(sid)
    existing = merge_session_fields(existing, fields)
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


def list_session_files(*, root: Path | None = None) -> list[dict[str, Any]]:
    """Load all session JSON payloads under the store directory."""
    base = root if root is not None else Path(settings.session_store_dir)
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        if path.name in _RESERVED_BASENAMES:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("session_id"):
                out.append(data)
        except (OSError, json.JSONDecodeError):
            continue
    return out
