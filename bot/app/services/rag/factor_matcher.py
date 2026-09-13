"""Map encoder checklist items to red-flag graph Factor names (regex-first).

When ``DIGIMSK_LLM_FACTOR_MATCH=1``, unmatched (non-gated) rows get one batched
LLM cross-check against the inventory Factor list before GraphRAG traversal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas import ChecklistItem, ChecklistItemDump
from app.services.graphrag.neo4j_config import DEFAULT_INVENTORY_PATH
from app.services.graphrag.schemas import FactorMatch, FactorMention
from app.services.rag.factor_patterns import (
    _age_implies_over_50,
    _norm,
    _severity_implies_severe,
    _sex_factor,
    build_factor_patterns,
    load_factor_names,
)
from app.services.rag.factor_polarity import (
    FACTOR_STATE_AFFIRMED,
    FACTOR_STATE_DENIED,
    FACTOR_STATE_UNKNOWN,
    FactorPolarity,
    map_span_into_message,
    polarity_for_span,
)
from app.services.rag.llm_factor_match import llm_match_unmatched_factors


@dataclass(frozen=True)
class _Hit:
    factor_name: str
    method: str
    score: float
    polarity: FactorPolarity
    start: int
    end: int


def match_is_affirmed(match: FactorMatch) -> bool:
    """True when this match may seed traversal / matched_factors."""
    if not match.factor_name:
        return False
    return match.polarity != FACTOR_STATE_DENIED


def affirmed_factor_names(matches: list[FactorMatch]) -> list[str]:
    """Unique affirmed Factor names, including extra mentions on mixed items."""
    seen: set[str] = set()
    out: list[str] = []

    def _add(name: str | None) -> None:
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    for match in matches:
        if match_is_affirmed(match):
            _add(match.factor_name)
        for mention in match.mentions:
            if mention.polarity == FACTOR_STATE_AFFIRMED:
                _add(mention.factor_name)
    return out


def merge_factor_states(
    existing: dict[str, str] | None,
    matches: list[FactorMatch],
) -> dict[str, str]:
    """Sticky per-session polarity: later affirms override denials and vice versa."""
    out = {
        key: value
        for key, value in (existing or {}).items()
        if value in {FACTOR_STATE_AFFIRMED, FACTOR_STATE_DENIED}
    }
    turn: dict[str, set[str]] = {}

    def _note(name: str | None, polarity: str | None) -> None:
        if not name or polarity not in {FACTOR_STATE_AFFIRMED, FACTOR_STATE_DENIED}:
            return
        turn.setdefault(name, set()).add(polarity)

    for match in matches:
        if match.factor_name:
            _note(
                match.factor_name,
                match.polarity or (FACTOR_STATE_AFFIRMED if match.factor_name else None),
            )
        for mention in match.mentions:
            _note(mention.factor_name, mention.polarity)

    for name, polarities in turn.items():
        # Same-turn mixed spans for one factor: keep the true positive.
        if FACTOR_STATE_AFFIRMED in polarities:
            out[name] = FACTOR_STATE_AFFIRMED
        elif FACTOR_STATE_DENIED in polarities:
            out[name] = FACTOR_STATE_DENIED
    return out


def apply_factor_states(state: dict, matches: list[FactorMatch]) -> dict[str, str]:
    merged = merge_factor_states(state.get("factor_states"), matches)
    state["factor_states"] = merged
    return merged


def update_factor_states_from_checklist(
    state: dict,
    *,
    skip_llm: bool = True,
) -> dict[str, str]:
    """Refresh ``state['factor_states']`` from the current checklist + user text.

    The raw message is scored as well so a denial still lands when the encoder
    stored a negation-stripped entity span.
    """
    checklist = state.get("clinical_checklist") or []
    message = str(state.get("message") or state.get("message_normalized") or "").strip()
    matches = match_checklist_to_factors(
        checklist,
        source_message=message or None,
        skip_llm=skip_llm,
    )
    if message:
        matches = [
            *matches,
            *match_checklist_to_factors(
                [
                    ChecklistItem(
                        text=message,
                        kind="other",
                        source="user_message",
                        label="",
                    )
                ],
                source_message=message,
                skip_llm=True,
            ),
        ]
    return apply_factor_states(state, matches)


def _polarity_at(
    item_text: str,
    start: int,
    end: int,
    source_message: str | None,
) -> str:
    ctx, mapped_start, mapped_end = map_span_into_message(
        item_text, start, end, source_message
    )
    return polarity_for_span(ctx, mapped_start, mapped_end)


def _first_token_span(text: str, tokens: set[str]) -> tuple[int, int] | None:
    low = text.casefold()
    best: tuple[int, int] | None = None
    for token in tokens:
        if not token:
            continue
        match = re.search(rf"\b{re.escape(token)}\b", low)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), match.end())
    return best


def _mention(hit: _Hit) -> FactorMention:
    return FactorMention(
        factor_name=hit.factor_name,
        polarity=hit.polarity,
        match_method=hit.method,
        match_score=hit.score,
    )


def _match_from_hits(
    dumped: dict,
    hits: list[_Hit],
    *,
    fallback: FactorMatch | None = None,
) -> FactorMatch:
    if not hits:
        return fallback or FactorMatch(
            checklist_item=dumped, match_method="none", match_score=0.0
        )
    mentions = [_mention(hit) for hit in hits]
    affirmed = [hit for hit in hits if hit.polarity == FACTOR_STATE_AFFIRMED]
    denied = [hit for hit in hits if hit.polarity == FACTOR_STATE_DENIED]
    primary = max(affirmed or denied, key=lambda hit: hit.score)
    return FactorMatch(
        checklist_item=dumped,
        factor_name=primary.factor_name,
        match_method=primary.method,
        match_score=primary.score,
        polarity=primary.polarity,
        mentions=mentions,
    )


def _match_item_to_factor(
    item: ChecklistItem,
    factors: tuple[str, ...],
    patterns: tuple,
    *,
    source_message: str | None = None,
) -> FactorMatch:
    text = (item.text or "").strip()
    dumped = item.model_dump()
    if not text:
        return FactorMatch(checklist_item=dumped, match_method="empty", match_score=0.0)

    low = _norm(text)
    factor_set = set(factors)
    hits: list[_Hit] = []
    seen: set[tuple[str, str]] = set()

    def _add(factor: str, method: str, score: float, start: int, end: int) -> None:
        polarity = _polarity_at(text, start, end, source_message)
        if polarity == FACTOR_STATE_UNKNOWN:
            return
        key = (factor, polarity)
        if key in seen:
            return
        seen.add(key)
        hits.append(
            _Hit(
                factor_name=factor,
                method=method,
                score=score,
                polarity=polarity,
                start=start,
                end=end,
            )
        )

    if item.kind == "demographic" and item.label == "age":
        if _age_implies_over_50(text) and "Age over 50" in factor_set:
            _add("Age over 50", "checklist_kind", 1.0, 0, len(text))
            return _match_from_hits(dumped, hits)
        # Under-50 (or non-numeric) age rows must not match via other shortcuts.
        return FactorMatch(
            checklist_item=dumped,
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )

    if item.kind == "severity" and item.label == "symptom_severity":
        if _severity_implies_severe(text) and "Severe pain" in factor_set:
            _add("Severe pain", "checklist_kind", 1.0, 0, len(text))
            return _match_from_hits(dumped, hits)
        return FactorMatch(
            checklist_item=dumped,
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )

    if item.kind == "demographic" and item.label == "sex":
        sex_factor = _sex_factor(text)
        if sex_factor and sex_factor in factor_set:
            _add(sex_factor, "checklist_kind", 1.0, 0, len(text))
            return _match_from_hits(dumped, hits)

    for fp in patterns:
        if fp.checklist_kinds and item.kind not in fp.checklist_kinds:
            continue
        if fp.checklist_labels and item.label not in fp.checklist_labels:
            continue
        if fp.checklist_kinds and fp.checklist_labels and fp.factor_name in factor_set:
            # Sex / age / severity handled above with text predicates.
            if item.kind == "demographic" and item.label in ("sex", "age"):
                continue
            if item.kind == "severity" and item.label == "symptom_severity":
                continue
            span_start, span_end = 0, len(text)
            for pat in fp.patterns:
                found = pat.search(text) or pat.search(low)
                if found:
                    span_start, span_end = found.start(), found.end()
                    break
            _add(fp.factor_name, "checklist_kind", 0.95, span_start, span_end)
            continue

        for pat in fp.patterns:
            found = pat.search(text) or pat.search(low)
            if not found:
                continue
            score = 0.98 if fp.priority >= 10 else 0.9
            method = "regex" if fp.priority < 10 else "checklist_kind"
            _add(fp.factor_name, method, score, found.start(), found.end())

    if hits:
        return _match_from_hits(dumped, hits)

    best_name: str | None = None
    best_score = 0.0
    best_tokens: set[str] = set()
    text_tokens = set(low.split())
    for factor in factors:
        factor_low = _norm(factor)
        if low == factor_low:
            _add(factor, "factor_name_exact", 1.0, 0, len(text))
            return _match_from_hits(dumped, hits)
        if item.kind == "demographic" and item.label == "sex":
            continue
        factor_tokens = set(factor_low.split())
        if not factor_tokens:
            continue
        overlap = len(text_tokens & factor_tokens) / len(factor_tokens)
        score = overlap * 0.75
        if score > best_score:
            best_score = score
            best_name = factor
            best_tokens = factor_tokens

    if best_name and best_score >= 0.75:
        span = _first_token_span(text, best_tokens) or (0, len(text))
        polarity = _polarity_at(text, span[0], span[1], source_message)
        # Fuzzy denials score higher than affirmations (the phrase contains the
        # factor name). Never affirm from fuzzy when the span is negated.
        if polarity == FACTOR_STATE_DENIED:
            _add(best_name, "fuzzy_fallback", best_score, span[0], span[1])
            return _match_from_hits(dumped, hits)
        if polarity == FACTOR_STATE_AFFIRMED:
            return FactorMatch(
                checklist_item=dumped,
                factor_name=best_name,
                match_method="fuzzy_fallback",
                match_score=best_score,
                polarity=FACTOR_STATE_AFFIRMED,
                mentions=[
                    FactorMention(
                        factor_name=best_name,
                        polarity=FACTOR_STATE_AFFIRMED,
                        match_method="fuzzy_fallback",
                        match_score=best_score,
                    )
                ],
            )

    return FactorMatch(
        checklist_item=dumped,
        factor_name=None,
        match_method="none",
        match_score=best_score,
    )


def _gap_for_match(match: FactorMatch) -> dict[str, str] | None:
    """Classify coverage gaps / suspect matches for session audit."""
    item = match.checklist_item or {}
    kind = str(item.get("kind") or "")
    label = str(item.get("label") or "")
    text = str(item.get("text") or "").strip()

    if match.match_method == "empty":
        return {
            "code": "empty_text",
            "detail": "Checklist item has empty text; no Factor can be matched.",
        }
    if kind == "severity" and label == "symptom_severity" and not match.factor_name:
        return {
            "code": "severity_below_threshold",
            "detail": (
                f"Severity {text!r} did not meet severe criteria "
                "(numeric ≥7 or severe-class words)."
            ),
        }
    if kind == "demographic" and label == "age" and not match.factor_name:
        return {
            "code": "age_below_threshold",
            "detail": f"Age {text!r} did not imply ≥50; Age over 50 not applied.",
        }
    if kind == "demographic" and label == "sex" and not match.factor_name:
        return {
            "code": "sex_unresolved",
            "detail": f"Sex text {text!r} did not map to Male sex / Female sex.",
        }
    if (
        match.match_method == "fuzzy_fallback"
        and match.factor_name
        and match.polarity != FACTOR_STATE_DENIED
    ):
        return {
            "code": "fuzzy_match",
            "detail": (
                f"Low-confidence fuzzy attach of {text!r} → {match.factor_name!r} "
                f"(score={match.match_score:.2f}); review for false positive."
            ),
        }
    if (
        match.factor_name == "Constant pain"
        and kind == "palliative"
        and label == "rest"
        and match.match_method == "checklist_kind"
    ):
        return {
            "code": "suspect_blind_kind_map",
            "detail": (
                "palliative/rest mapped to Constant pain via kind/label only; "
                "rest relief is clinically inverted vs constant pain."
            ),
        }
    if not match.factor_name:
        return {
            "code": "unmatched",
            "detail": (
                f"No graph Factor matched for {text!r} "
                f"(kind={kind!r}, label={label!r})."
            ),
        }
    return None


def build_factor_matching_audit(
    matches: list[FactorMatch],
) -> dict[str, Any]:
    """Serialize per-item factor matching decisions for session / UI logging."""
    items: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    methods: dict[str, int] = {}
    matched_names: list[str] = []
    denied_names: list[str] = []
    seen_factors: set[str] = set()
    seen_denied: set[str] = set()

    for match in matches:
        gap = _gap_for_match(match)
        status = "matched" if match_is_affirmed(match) else "unmatched"
        if match.factor_name and match.polarity == FACTOR_STATE_DENIED:
            status = "denied"
        if gap and gap["code"] in {
            "severity_below_threshold",
            "age_below_threshold",
            "sex_unresolved",
        }:
            status = "gated"
        entry: dict[str, Any] = {
            "checklist_item": dict(match.checklist_item or {}),
            "factor_name": match.factor_name,
            "match_method": match.match_method,
            "match_score": round(float(match.match_score), 4),
            "status": status,
            "polarity": match.polarity,
            "gap": gap,
        }
        items.append(entry)
        methods[match.match_method] = methods.get(match.match_method, 0) + 1
        if match_is_affirmed(match) and match.factor_name not in seen_factors:
            seen_factors.add(match.factor_name)
            matched_names.append(match.factor_name)
        if match.polarity == FACTOR_STATE_DENIED and match.factor_name:
            if match.factor_name not in seen_denied:
                seen_denied.add(match.factor_name)
                denied_names.append(match.factor_name)
        for mention in match.mentions:
            if mention.polarity == FACTOR_STATE_DENIED:
                if mention.factor_name not in seen_denied:
                    seen_denied.add(mention.factor_name)
                    denied_names.append(mention.factor_name)
            elif mention.polarity == FACTOR_STATE_AFFIRMED:
                if mention.factor_name not in seen_factors:
                    seen_factors.add(mention.factor_name)
                    matched_names.append(mention.factor_name)
        if gap:
            gaps.append(
                {
                    "code": gap["code"],
                    "detail": gap["detail"],
                    "checklist_item": entry["checklist_item"],
                    "factor_name": match.factor_name,
                    "match_method": match.match_method,
                    "match_score": entry["match_score"],
                }
            )

    unmatched = [e for e in items if not e["factor_name"]]
    return {
        "summary": {
            "checklist_items": len(items),
            "matched_count": len(matched_names),
            "unmatched_count": len(unmatched),
            "gap_count": len(gaps),
            "matched_factors": matched_names,
            "denied_factors": denied_names,
            "methods": methods,
        },
        "items": items,
        "gaps": gaps,
        "matched": [e for e in items if e["status"] == "matched"],
        "unmatched": unmatched,
    }


def match_checklist_to_factors(
    items: list[ChecklistItem] | list[ChecklistItemDump],
    *,
    inventory_path: Path | None = None,
    source_message: str | None = None,
    skip_llm: bool = False,
) -> list[FactorMatch]:
    """Resolve every checklist row to a Factor match (or unmatched / gated).

    One :class:`FactorMatch` is returned per input item so session audit trails
    can see coverage gaps. Callers that need unique Factor names should use
    :func:`affirmed_factor_names` (denied matches keep ``factor_name`` so the
    LLM path cannot re-affirm them).

    When LLM factor matching is enabled, unmatched non-gated rows may be filled
    with ``match_method="llm_semantic"`` after the deterministic pass.
    ``skip_llm`` is for question-turn ``factor_states`` updates so intake does
    not pay an extra generator call.
    """
    inv = str(inventory_path or DEFAULT_INVENTORY_PATH)
    factors = load_factor_names(inv)
    patterns = build_factor_patterns(inv)
    parsed: list[ChecklistItem] = []
    for row in items:
        if isinstance(row, ChecklistItem):
            parsed.append(row)
        else:
            parsed.append(ChecklistItem.model_validate(row))

    matches = [
        _match_item_to_factor(
            item, factors, patterns, source_message=source_message
        )
        for item in parsed
    ]
    if skip_llm:
        return matches
    return llm_match_unmatched_factors(matches, factors)
