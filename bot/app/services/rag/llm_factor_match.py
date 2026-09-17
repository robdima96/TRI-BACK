"""LLM cross-check for unmatched checklist items → inventory Factor names.

Runs when ``settings.llm_factor_match`` is on for unmatched (non-gated)
checklist deltas during intake. This is the remaining semantic Factor path;
disposition does not rematch old rows with ``llm_semantic``. Proposals must
name a Factor that exists in the inventory; abstention (null) is the
correct outcome when no graph Factor fits. One row may map to several
Factors, each with polarity.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.schemas import ChecklistItem
from app.services.generator import generate_from_messages, generator_model_configured
from app.services.graphrag.schemas import FactorMatch, FactorMention
from app.services.rag.factor_polarity import (
    FACTOR_STATE_AFFIRMED,
    FACTOR_STATE_DENIED,
)

_log = logging.getLogger(__name__)

LLM_FACTOR_MATCH_MAX_TOKENS = 1024
LLM_FACTOR_MATCH_TEMPERATURE = 0.1
MIN_CONFIDENCE = 0.7

_ALLOWED_POLARITIES = frozenset({FACTOR_STATE_AFFIRMED, FACTOR_STATE_DENIED})

# Palliative rows must not be remapped onto provocative / onset Factors.
_PALLIATIVE_INCOMPATIBLE: frozenset[str] = frozenset(
    {
        "Activity-related onset",
        "Heavy lifting",
        "Prolonged sitting aggravates",
    }
)

FACTOR_MATCH_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "matches": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "index": {"type": "INTEGER"},
                    "factor_name": {"type": "STRING", "nullable": True},
                    "polarity": {"type": "STRING", "nullable": True},
                    "confidence": {"type": "NUMBER"},
                    "reason": {"type": "STRING"},
                },
                "required": ["index", "factor_name", "confidence", "reason"],
            },
        }
    },
    "required": ["matches"],
}

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)

# Deterministic gates already decided "none" intentionally — never re-open.
_GATED_KIND_LABELS: frozenset[tuple[str, str]] = frozenset(
    {
        ("demographic", "age"),
        ("demographic", "sex"),
        ("severity", "symptom_severity"),
    }
)


def eligible_for_llm_match(match: FactorMatch) -> bool:
    """True when the deterministic pass left a non-gated gap worth asking the LLM."""
    if match.factor_name:
        return False
    if match.match_method != "none":
        return False
    item = match.checklist_item or {}
    text = str(item.get("text") or "").strip()
    if not text:
        return False
    kind = str(item.get("kind") or "").strip()
    label = str(item.get("label") or "").strip()
    if (kind, label) in _GATED_KIND_LABELS:
        return False
    return True


def _canonical_factor(name: str, factors: tuple[str, ...]) -> str | None:
    key = (name or "").strip().casefold()
    if not key:
        return None
    by_cf = {f.casefold(): f for f in factors}
    return by_cf.get(key)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    fence = _JSON_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _kind_compatible(kind: str, factor_name: str) -> bool:
    if kind == "palliative" and factor_name in _PALLIATIVE_INCOMPATIBLE:
        return False
    return True


def _build_messages(
    candidates: list[tuple[int, ChecklistItem]],
    factors: tuple[str, ...],
) -> list[dict[str, str]]:
    rows: list[str] = []
    for idx, item in candidates:
        rows.append(
            f"{idx}. text={item.text!r} kind={item.kind!r} label={item.label!r}"
        )
    factor_block = "\n".join(f"- {name}" for name in factors)
    instruction = (
        "You map musculoskeletal triage checklist findings to canonical red-flag "
        "graph Factor names.\n\n"
        "Rules:\n"
        "- Use ONLY Factor names from the inventory list below (exact spelling).\n"
        "- Map a row only when the patient statement clearly implies that Factor.\n"
        "- One row may map to SEVERAL inventory Factors. Repeat the same index "
        "once per Factor, each with its own polarity.\n"
        "- polarity is affirmed or denied. Prefer factor_name=null (abstain) when "
        "no inventory Factor fits, when the row is a body part / duration / "
        "generic symptom without a Factor twin, or when the mapping would stretch "
        "meaning (e.g. standing intolerance is not Prolonged sitting aggravates).\n"
        "- Kind compatibility: a palliative (makes it better) row must not map to "
        "Activity-related onset, Heavy lifting, or Prolonged sitting aggravates. "
        "Abstain instead of remapping.\n"
        "- Avoid span-negation mistakes: 'It's pretty stiff so I don't move it a "
        "lot' affirms Lumbar stiffness AND Movement-related pain (guarding), not "
        "a denial of movement-related pain.\n"
        "- Do not invent diagnoses or Factor names.\n"
        "- confidence is 0.0–1.0; only propose a Factor when confidence >= "
        f"{MIN_CONFIDENCE:.2f}.\n\n"
        "INVENTORY FACTORS:\n"
        f"{factor_block}\n\n"
        "CHECKLIST ROWS TO JUDGE (1-based indexes; repeat an index for 1:many):\n"
        + "\n".join(rows)
        + "\n\n"
        "Respond with ONE JSON object only:\n"
        "{\n"
        '  "matches": [\n'
        '    {"index": 1, "factor_name": "Lumbar stiffness", "polarity": "affirmed", '
        '"confidence": 0.92, "reason": "stiff implies lumbar stiffness"},\n'
        '    {"index": 1, "factor_name": "Movement-related pain", "polarity": "affirmed", '
        '"confidence": 0.88, "reason": "avoids moving because it hurts"},\n'
        '    {"index": 2, "factor_name": null, "polarity": null, "confidence": 0.0, '
        '"reason": "body part only; no Factor"}\n'
        "  ]\n"
        "}\n"
        "Include every input index at least once (null if abstaining)."
    )
    return [{"role": "user", "content": instruction}]


def _parse_proposals(
    payload: dict[str, Any],
    *,
    valid_indexes: set[int],
    factors: tuple[str, ...],
    items_by_index: dict[int, ChecklistItem],
) -> dict[int, list[tuple[str, str, float]]]:
    """Return index → [(canonical_factor, polarity, confidence), ...]."""
    raw_list = payload.get("matches")
    if not isinstance(raw_list, list):
        return {}

    accepted: dict[int, list[tuple[str, str, float]]] = {}
    seen: dict[int, set[str]] = {}
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("index"))
        except (TypeError, ValueError):
            continue
        if idx not in valid_indexes:
            continue

        raw_name = entry.get("factor_name")
        if raw_name is None or (isinstance(raw_name, str) and not raw_name.strip()):
            continue
        if not isinstance(raw_name, str):
            continue

        try:
            confidence = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < MIN_CONFIDENCE:
            _log.debug(
                "llm factor match rejected low confidence idx=%s name=%r conf=%s",
                idx,
                raw_name,
                confidence,
            )
            continue

        canonical = _canonical_factor(raw_name, factors)
        if not canonical:
            _log.info(
                "llm factor match rejected unknown factor idx=%s name=%r",
                idx,
                raw_name,
            )
            continue

        polarity = str(entry.get("polarity") or FACTOR_STATE_AFFIRMED).strip().casefold()
        if polarity not in _ALLOWED_POLARITIES:
            continue

        item = items_by_index.get(idx)
        kind = str(getattr(item, "kind", None) or "")
        if not _kind_compatible(kind, canonical):
            _log.info(
                "llm factor match rejected kind-incompatible idx=%s kind=%r name=%r",
                idx,
                kind,
                canonical,
            )
            continue

        names = seen.setdefault(idx, set())
        if canonical in names:
            continue
        names.add(canonical)
        accepted.setdefault(idx, []).append(
            (canonical, polarity, min(1.0, confidence))
        )
    return accepted


def llm_match_unmatched_factors(
    matches: list[FactorMatch],
    factors: tuple[str, ...],
) -> list[FactorMatch]:
    """Fill unmatched gaps via one batched LLM call; leave others unchanged.

    Failures (flag off, generator unavailable, parse error) return ``matches``
    unchanged so GraphRAG never blocks on this path.
    """
    from app.config import settings

    if not settings.llm_factor_match:
        return matches
    if not factors:
        return matches
    if not generator_model_configured():
        _log.warning("llm factor match skipped: generator not configured")
        return matches

    candidates: list[tuple[int, ChecklistItem]] = []
    for i, match in enumerate(matches):
        if not eligible_for_llm_match(match):
            continue
        item = ChecklistItem.model_validate(match.checklist_item or {})
        # 1-based indexes in the prompt
        candidates.append((i + 1, item))

    if not candidates:
        return matches

    try:
        raw = generate_from_messages(
            _build_messages(candidates, factors),
            max_new_tokens=LLM_FACTOR_MATCH_MAX_TOKENS,
            temperature=LLM_FACTOR_MATCH_TEMPERATURE,
            response_mime_type="application/json",
            response_schema=FACTOR_MATCH_RESPONSE_SCHEMA,
        )
    except Exception as exc:
        _log.exception("llm factor match call failed: %s", exc)
        return matches

    payload = _extract_json_object(raw)
    if not payload:
        _log.info("llm factor match parse failed raw=%r", (raw or "")[:240])
        return matches

    valid_indexes = {idx for idx, _ in candidates}
    items_by_index = {idx: item for idx, item in candidates}
    accepted = _parse_proposals(
        payload,
        valid_indexes=valid_indexes,
        factors=factors,
        items_by_index=items_by_index,
    )
    if not accepted:
        _log.info(
            "llm factor match: %d candidates, 0 accepted (abstention or reject)",
            len(candidates),
        )
        return matches

    out = list(matches)
    accepted_names: list[str] = []
    for prompt_idx, proposals in accepted.items():
        list_idx = prompt_idx - 1
        prior = out[list_idx]
        mentions = [
            FactorMention(
                factor_name=name,
                polarity=polarity,  # type: ignore[arg-type]
                match_method="llm_semantic",
                match_score=confidence,
            )
            for name, polarity, confidence in proposals
        ]
        affirmed = [p for p in proposals if p[1] == FACTOR_STATE_AFFIRMED]
        denied = [p for p in proposals if p[1] == FACTOR_STATE_DENIED]
        primary = (affirmed or denied)[0]
        out[list_idx] = FactorMatch(
            checklist_item=dict(prior.checklist_item or {}),
            factor_name=primary[0],
            match_method="llm_semantic",
            match_score=primary[2],
            polarity=primary[1],  # type: ignore[arg-type]
            mentions=mentions,
        )
        accepted_names.extend(name for name, _, _ in proposals)
    _log.info(
        "llm factor match: %d candidates, %d accepted → %s",
        len(candidates),
        len(accepted_names),
        accepted_names,
    )
    return out
