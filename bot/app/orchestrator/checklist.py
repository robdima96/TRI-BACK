"""Clinical checklist merge and stable row identity helpers."""

from __future__ import annotations

import uuid
from typing import Any

from app.schemas import ChecklistItem


def new_checklist_id() -> str:
    """Opaque stable id for a checklist row (not position-based)."""
    return f"cl_{uuid.uuid4().hex[:12]}"


def _coerce_confirmed(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes"}
    return bool(value)


def ensure_row_identity(row: dict[str, Any]) -> dict[str, Any]:
    """Copy a checklist row, assigning ``id`` and normalizing ``confirmed`` if needed."""
    out = dict(row)
    raw_id = str(out.get("id") or "").strip()
    if not raw_id:
        out["id"] = new_checklist_id()
    else:
        out["id"] = raw_id
    if "confirmed" in out:
        out["confirmed"] = _coerce_confirmed(out.get("confirmed"))
    else:
        out["confirmed"] = False
    return out


def ensure_checklist_ids(checklist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every row has a stable ``id`` and a boolean ``confirmed`` flag."""
    return [ensure_row_identity(row) for row in checklist]


def content_dedupe_key(d: dict[str, Any] | ChecklistItem) -> tuple[str, str, str, str]:
    """Dedupe key ignores id/confirmed so the same clinical fact is not duplicated."""
    if isinstance(d, ChecklistItem):
        return (d.text, d.kind, d.source, d.label)
    return (
        str(d.get("text", "")),
        str(d.get("kind", "")),
        str(d.get("source", "")),
        str(d.get("label", "")),
    )


# Clinical topic family for modify guards (confirmed rows cannot jump families).
_NER_LABEL_FAMILY: dict[str, str] = {
    "symptom": "symptom",
    "symptom duration": "duration",
    "symptom quality": "symptom_quality",
    "symptom severity": "severity",
    "symptom provocative factor": "provocative",
    "symptom palliative factor": "palliative",
    "body part": "body_part",
    "sign": "sign",
}


def kind_family(kind: str, label: str = "") -> str:
    """Map kind(+ner label) to a clinical family used by confirmed-row modify guards."""
    k = (kind or "").strip().casefold()
    lab = (label or "").strip().casefold()
    if k == "ner_entity":
        return _NER_LABEL_FAMILY.get(lab, f"ner_entity:{lab}" if lab else "ner_entity")
    return k


def merge_checklist_items(
    prior: list[dict[str, Any]],
    current_items: list[ChecklistItem],
) -> list[dict[str, Any]]:
    """Dedupe by (text, kind, source, label); append new items; preserve prior ids."""

    out: list[dict[str, Any]] = ensure_checklist_ids([dict(x) for x in prior])
    seen = {content_dedupe_key(i) for i in out}
    for it in current_items:
        d = it.model_dump()
        key = content_dedupe_key(d)
        if key in seen:
            continue
        if not str(d.get("id") or "").strip():
            d["id"] = new_checklist_id()
        d["confirmed"] = _coerce_confirmed(d.get("confirmed", False))
        seen.add(key)
        out.append(d)
    return out
