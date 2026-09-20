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
    PRESERVE_IF_EMPTY_KEYS,
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


def merge_messages_preserving_study(
    existing_messages: list[Any] | None,
    incoming_messages: list[Any] | None,
) -> list[dict[str, Any]]:
    """Keep study overlay fields (feedback, message_id, …) when the bot rewrites messages.

    Aligns by index when ``role``+``content`` match, otherwise by the same pair
    anywhere in the prior transcript.

    Also keeps leading study-only assistant rows (e.g. canned ``msg_intro``) that
    never appear in the bot LangGraph transcript.
    """
    old = [m for m in (existing_messages or []) if isinstance(m, dict)]
    new = [dict(m) for m in (incoming_messages or []) if isinstance(m, dict)]
    if not old:
        return new
    if not new:
        return old

    preserve_keys = (
        "message_id",
        "feedback",
        "reasoning_text",
        "graph_json",
        "has_graph",
        "timestamp",
        "citations",
        "rephrased",
        "question_mode",
    )

    def _feedback_has_rating(fb: Any) -> bool:
        return isinstance(fb, dict) and bool(fb.get("rating"))

    def _same_turn(a: dict[str, Any], b: dict[str, Any]) -> bool:
        return a.get("role") == b.get("role") and a.get("content") == b.get("content")

    def _find_prior(msg: dict[str, Any], index: int) -> dict[str, Any] | None:
        if index < len(old):
            cand = old[index]
            if _same_turn(cand, msg):
                return cand
            if cand.get("role") == msg.get("role") and cand.get("rephrased"):
                return cand
        for cand in old:
            if _same_turn(cand, msg):
                return cand
        return None

    def _in_new(cand: dict[str, Any]) -> bool:
        return any(_same_turn(cand, msg) for msg in new)

    # Study-only prefix (canned intro): leading assistants absent from bot transcript.
    prefix: list[dict[str, Any]] = []
    for cand in old:
        if cand.get("role") != "assistant":
            break
        if _in_new(cand):
            break
        prefix.append(dict(cand))

    for i, msg in enumerate(new):
        prev = _find_prior(msg, i)
        if not prev:
            continue
        if prev.get("rephrased") and prev.get("content"):
            msg["content"] = prev["content"]
            msg["rephrased"] = True
        for key in preserve_keys:
            if key == "feedback":
                if not _feedback_has_rating(msg.get("feedback")) and _feedback_has_rating(
                    prev.get("feedback")
                ):
                    msg["feedback"] = prev["feedback"]
                continue
            incoming_val = msg.get(key)
            prior_val = prev.get(key)
            if incoming_val in (None, "", []) and prior_val not in (None, "", []):
                msg[key] = prior_val
    return prefix + new


def _merge_turn_histories(
    existing: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Keep earlier turns when a reset checkpoint would send a shorter history.

    Same ``turn_index`` is replaced. If incoming looks like a restarted thread
    (max index behind existing), append the latest incoming row as the next turn.
    """
    prior = [row for row in (existing or []) if isinstance(row, dict)]
    new = [row for row in (incoming or []) if isinstance(row, dict)]
    if not new:
        return prior
    if not prior:
        return new
    exist_max = max(int(row.get("turn_index") or 0) for row in prior)
    inc_max = max(int(row.get("turn_index") or 0) for row in new)
    if inc_max >= exist_max and len(new) >= len(prior):
        by_index: dict[int, dict[str, Any]] = {}
        for row in prior:
            idx = row.get("turn_index")
            if idx is not None:
                by_index[int(idx)] = row
        for row in new:
            idx = row.get("turn_index")
            if idx is not None:
                by_index[int(idx)] = row
        return [by_index[k] for k in sorted(by_index)]
    last = dict(new[-1])
    last["turn_index"] = exist_max + 1
    return prior + [last]


def merge_session_fields(existing: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Merge a turn update into the session snapshot without wiping disposition.

    - ``disposition`` / ``orchestrator`` records append to history lists.
    - Empty/None disposition snapshot fields from a question turn do not clear
      previously stored graph / factor / agent audits.
    - Incoming ``messages`` keep prior study feedback / message_id overlays.
    """
    merged = dict(existing)
    incoming = dict(fields)

    disposition = incoming.pop("disposition", None)
    orchestrator = incoming.pop("orchestrator", None)
    intake = incoming.pop("intake", None)

    if "messages" in incoming:
        incoming["messages"] = merge_messages_preserving_study(
            merged.get("messages"),
            incoming.get("messages"),
        )

    if "factor_states" in incoming and isinstance(incoming.get("factor_states"), dict):
        prior_states = merged.get("factor_states")
        prior = prior_states if isinstance(prior_states, dict) else {}
        incoming["factor_states"] = {**prior, **incoming["factor_states"]}

    if "extraction_history" in incoming:
        incoming["extraction_history"] = _merge_turn_histories(
            merged.get("extraction_history")
            if isinstance(merged.get("extraction_history"), list)
            else None,
            incoming.get("extraction_history")
            if isinstance(incoming.get("extraction_history"), list)
            else None,
        )

    # Never let callers null-out durable graph snapshots.
    for key in PRESERVE_IF_EMPTY_KEYS:
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
        if disposition.get("intake_traversal") not in (None, {}, []):
            merged["intake_traversal"] = disposition["intake_traversal"]

    if intake and isinstance(intake, dict):
        merged["intake_history"] = _append_by_turn_index(
            merged.get("intake_history"),
            intake,
        )
        if intake.get("intake_traversal") not in (None, {}, []):
            merged["intake_traversal"] = intake["intake_traversal"]
        if isinstance(intake.get("factor_states"), dict) and intake["factor_states"]:
            prior_states = merged.get("factor_states")
            prior = prior_states if isinstance(prior_states, dict) else {}
            merged["factor_states"] = {**prior, **intake["factor_states"]}

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
    data = json.dumps(existing, ensure_ascii=False, indent=2)
    tmp.write_text(data, encoding="utf-8")
    try:
        tmp.replace(path)
    except OSError:
        # GCS FUSE often cannot rename; write in place instead.
        path.write_text(data, encoding="utf-8")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


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
