"""Load and summarize TRI-BACK bot session JSON files for the Testing browser."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Repo root = TRI-BACK clone (Testing/ is one level down).
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS_DIR = REPO_ROOT / "bot" / "data" / "sessions"

_STUDY_ID_RE = re.compile(r"^[A-Za-z0-9]+_[0-9]+$")


def sessions_dir() -> Path:
    return DEFAULT_SESSIONS_DIR


def _parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    local = dt.astimezone() if dt.tzinfo else dt.replace(tzinfo=timezone.utc).astimezone()
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _session_activity_time(data: dict[str, Any], path: Path) -> datetime:
    """Best-effort last activity: engagement / extraction / file mtime (UTC)."""
    candidates: list[datetime] = []
    for turn in (data.get("engagement") or {}).get("turns") or []:
        parsed = _parse_iso(turn.get("timestamp"))
        if parsed:
            candidates.append(_as_utc(parsed))
    for rec in data.get("extraction_history") or []:
        parsed = _parse_iso(rec.get("timestamp"))
        if parsed:
            candidates.append(_as_utc(parsed))
    for rec in data.get("orchestrator_history") or []:
        parsed = _parse_iso(rec.get("timestamp"))
        if parsed:
            candidates.append(_as_utc(parsed))
    for msg in data.get("messages") or []:
        if isinstance(msg, dict):
            parsed = _parse_iso(msg.get("timestamp"))
            if parsed:
                candidates.append(_as_utc(parsed))
    if candidates:
        return max(candidates)
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def list_session_summaries(
    root: Path | None = None,
    *,
    include_reference: bool = True,
) -> list[dict[str, Any]]:
    """Return session cards newest-first (by last activity)."""
    base = root or sessions_dir()
    if not base.is_dir():
        return []

    out: list[dict[str, Any]] = []
    for path in base.glob("*.json"):
        is_ref = path.name == "test_log.json"
        if is_ref and not include_reference:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        sid = str(data.get("session_id") or path.stem).strip() or path.stem
        activity = _session_activity_time(data, path)
        messages = data.get("messages") or []
        user_turns = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
        eng = data.get("engagement") or {}
        out.append(
            {
                "file_key": path.stem,
                "filename": path.name,
                "session_id": sid,
                "is_study_id": bool(_STUDY_ID_RE.match(sid)),
                "is_reference": is_ref,
                "activity_iso": _as_utc(activity).isoformat(),
                "activity_ts": _as_utc(activity).timestamp(),
                "activity_display": _fmt_dt(activity),
                "mtime": path.stat().st_mtime,
                "message_count": len(messages),
                "user_turns": user_turns,
                "checklist_count": len(data.get("clinical_checklist") or []),
                "has_disposition": bool(
                    data.get("disposition_history")
                    or data.get("matched_factors")
                    or data.get("graph_traversal")
                ),
                "has_orchestrator": bool(
                    data.get("orchestrator") or data.get("orchestrator_history")
                ),
                "duration_sec": eng.get("session_duration_sec"),
                "mean_round_trip_ms": eng.get("mean_round_trip_ms"),
            }
        )

    out.sort(key=lambda row: row["activity_ts"], reverse=True)
    return out


def load_session_by_key(file_key: str, root: Path | None = None) -> dict[str, Any] | None:
    base = root or sessions_dir()
    # Prevent path traversal.
    safe = Path(file_key).name
    path = base / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data = dict(data)
    data["_file_key"] = safe
    data["_filename"] = path.name
    data["_activity_display"] = _fmt_dt(_session_activity_time(data, path))
    return data


def index_by_turn(records: list[dict[str, Any]] | None) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        try:
            idx = int(rec.get("turn_index"))
        except (TypeError, ValueError):
            continue
        out[idx] = rec
    return out


def build_chat_turns(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pair transcript messages with per-turn extraction / coverage / engagement."""
    extractions = index_by_turn(data.get("extraction_history"))
    orchestrators = index_by_turn(data.get("orchestrator_history"))
    if not orchestrators and isinstance(data.get("orchestrator"), dict):
        orch = data["orchestrator"]
        try:
            orchestrators[int(orch.get("turn_index"))] = orch
        except (TypeError, ValueError):
            pass
    engagements = index_by_turn((data.get("engagement") or {}).get("turns"))
    dispositions = index_by_turn(data.get("disposition_history"))

    turns: list[dict[str, Any]] = []
    turn_index = 0
    pending_user: dict[str, Any] | None = None

    for msg in data.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = str(msg.get("content") or "")
        if role == "user":
            if pending_user is not None:
                # User message without assistant reply yet.
                turns.append(pending_user)
            turn_index += 1
            pending_user = {
                "turn_index": turn_index,
                "user": content,
                "assistant": None,
                "user_timestamp": msg.get("timestamp"),
                "assistant_timestamp": None,
                "extraction": extractions.get(turn_index),
                "orchestrator": orchestrators.get(turn_index),
                "engagement": engagements.get(turn_index),
                "disposition": dispositions.get(turn_index),
            }
        elif role == "assistant":
            if pending_user is None:
                turn_index += 1
                pending_user = {
                    "turn_index": turn_index,
                    "user": None,
                    "assistant": content,
                    "user_timestamp": None,
                    "assistant_timestamp": msg.get("timestamp"),
                    "extraction": extractions.get(turn_index),
                    "orchestrator": orchestrators.get(turn_index),
                    "engagement": engagements.get(turn_index),
                    "disposition": dispositions.get(turn_index),
                }
            else:
                pending_user["assistant"] = content
                pending_user["assistant_timestamp"] = msg.get("timestamp")
            turns.append(pending_user)
            pending_user = None

    if pending_user is not None:
        turns.append(pending_user)
    return turns


def engagement_chart_payload(data: dict[str, Any]) -> dict[str, Any]:
    turns = (data.get("engagement") or {}).get("turns") or []
    labels: list[str] = []
    round_trip: list[float] = []
    words: list[int] = []
    idle: list[float] = []
    for t in turns:
        if not isinstance(t, dict):
            continue
        labels.append(f"T{t.get('turn_index', '?')}")
        round_trip.append(float(t.get("round_trip_ms") or 0))
        words.append(int(t.get("user_word_count") or 0))
        idle.append(float(t.get("idle_before_turn_sec") or 0))
    eng = data.get("engagement") or {}
    return {
        "labels": labels,
        "round_trip_ms": round_trip,
        "user_words": words,
        "idle_before_turn_sec": idle,
        "summary": {
            "total_user_words": eng.get("total_user_words", 0),
            "total_user_chars": eng.get("total_user_chars", 0),
            "mean_round_trip_ms": eng.get("mean_round_trip_ms", 0),
            "median_round_trip_ms": eng.get("median_round_trip_ms", 0),
            "session_duration_sec": eng.get("session_duration_sec", 0),
            "feedback_up_count": eng.get("feedback_up_count", 0),
            "feedback_down_count": eng.get("feedback_down_count", 0),
        },
    }


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
