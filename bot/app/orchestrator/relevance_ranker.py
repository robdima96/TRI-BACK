"""Deterministic intake ranker: one queue of floor slots + eligible graph factors.

Re-ranked every turn. The queue reorders; it does not enumerate the graph.
Affirmed factors in ``NON_SEED_FACTORS`` do not open one-hop neighbourhood.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

from app.orchestrator.intake_models import CoverageReport, SlotName
from app.services.agentic_graph_rag.ontology import RedFlagOntology
from app.triage_profiles import TriageProfile, get_triage_profile, load_ontology_for_profile
from app.services.rag.factor_polarity import (
    FACTOR_STATE_AFFIRMED,
    FACTOR_STATE_DENIED,
    FACTOR_STATE_UNKNOWN,
)

Kind = Literal["slot", "factor"]

# Affirmed factors that must not open one-hop graph questions.
# They still count as matched for disposition; they just do not seed new asks.
# Edit this list — names must match the v4 factor sheet exactly.
NON_SEED_FACTORS: tuple[str, ...] = (
    "Age over 50",
    "Male sex",
    "Female sex",
    "Hypertension",
    "Severe pain",
    "Diabetes",
    "Smoking"
)
# Backward-compatible alias for the same exclusion set.
DEMOGRAPHIC_SEED_FACTORS: frozenset[str] = frozenset(NON_SEED_FACTORS)

# LBP defaults; live ranking reads the same names from the active TriageProfile.
TIME_CRITICAL_CONDITIONS: tuple[str, ...] = get_triage_profile().time_critical_conditions
OTHER_HIGH_ACUITY_CONDITIONS: tuple[str, ...] = (
    get_triage_profile().other_high_acuity_conditions
)
MECHANICAL_CONDITION = get_triage_profile().mechanical_condition

TIER_ANCHOR = 0
TIER_TIME_CRITICAL = 1
TIER_DEMO_COMORBID = 2
TIER_OTHER_HIGH_ACUITY = 3
TIER_SYMPTOM_SLOTS = 4
TIER_MECHANICAL = 5

SLOT_TIER: dict[SlotName, int] = {
    "symptom_anchor": TIER_ANCHOR,
    "age": TIER_DEMO_COMORBID,
    "sex": TIER_DEMO_COMORBID,
    "comorbidities": TIER_DEMO_COMORBID,
    "symptom_quality": TIER_SYMPTOM_SLOTS,
    "symptom_severity": TIER_SYMPTOM_SLOTS,
    "provocative": TIER_SYMPTOM_SLOTS,
    "palliative": TIER_SYMPTOM_SLOTS,
    "symptom_duration": TIER_SYMPTOM_SLOTS,
}

TIER2_SLOT_ORDER: tuple[SlotName, ...] = ("age", "sex", "comorbidities")
TIER4_SLOT_ORDER: tuple[SlotName, ...] = (
    "symptom_quality",
    "symptom_severity",
    "provocative",
    "palliative",
    "symptom_duration",
)

def _condition_tier_map(profile: TriageProfile) -> dict[str, int]:
    return {
        **{name: TIER_TIME_CRITICAL for name in profile.time_critical_conditions},
        **{name: TIER_OTHER_HIGH_ACUITY for name in profile.other_high_acuity_conditions},
        profile.mechanical_condition: TIER_MECHANICAL,
    }


def _state_of(factor_states: dict[str, str] | None, factor: str) -> str:
    raw = _recorded_polarity(factor_states, factor)
    return raw if raw is not None else FACTOR_STATE_UNKNOWN


def _recorded_polarity(factor_states: dict[str, str] | None, factor: str) -> str | None:
    """Return affirmed|denied|unknown only when ``factor`` is already recorded.

    Missing keys stay None so the ranker can still ask them. Explicit
    ``unknown`` (patient said they do not know) is a recorded answer.
    """
    raw = (factor_states or {}).get(factor)
    if raw in {FACTOR_STATE_AFFIRMED, FACTOR_STATE_DENIED, FACTOR_STATE_UNKNOWN}:
        return raw
    return None


def _canonical_factor(name: str, ontology: RedFlagOntology) -> str | None:
    spec = ontology.get_factor_question_spec(name)
    if spec is not None:
        return spec.factor
    want = name.casefold().strip()
    for factor in ontology.all_factors:
        if factor.casefold() == want:
            return factor
    return None


def conditions_for_factor(factor: str, ontology: RedFlagOntology) -> tuple[str, ...]:
    return tuple(
        condition
        for condition in ontology.conditions
        if factor in ontology.factors_by_condition.get(condition, ())
    )


def condition_tier(condition: str, profile: TriageProfile | None = None) -> int:
    return _condition_tier_map(profile or get_triage_profile()).get(
        condition, TIER_MECHANICAL
    )


def best_condition_for_factor(
    factor: str,
    ontology: RedFlagOntology,
    *,
    prefer: Sequence[str] | None = None,
    profile: TriageProfile | None = None,
) -> str | None:
    conditions = conditions_for_factor(factor, ontology)
    if not conditions:
        return None
    preferred = set(prefer or ())
    ranked = sorted(
        conditions,
        key=lambda name: (
            0 if name in preferred else 1,
            condition_tier(name, profile),
            ontology.conditions.index(name)
            if name in ontology.conditions
            else len(ontology.conditions),
        ),
    )
    return ranked[0]


def clinical_finding_seeds(
    factor_states: dict[str, str] | None,
    matched_factors: Iterable[str] | None = None,
    *,
    ontology: RedFlagOntology | None = None,
) -> tuple[str, ...]:
    """Affirmed factors that may open one-hop neighbourhood.

    ``NON_SEED_FACTORS`` (demographics, hypertension, severe pain, …) are
    excluded: they remain matched for disposition but do not open new asks.
    """
    ont = ontology or load_ontology_for_profile()
    names: list[str] = []
    seen: set[str] = set()

    def _add(raw: str, *, assume_affirmed: bool = False) -> None:
        canonical = _canonical_factor(raw, ont)
        if not canonical or canonical in seen:
            return
        if canonical in NON_SEED_FACTORS:
            return
        polarity = _state_of(factor_states, canonical)
        if polarity == FACTOR_STATE_DENIED:
            return
        if polarity != FACTOR_STATE_AFFIRMED and not assume_affirmed:
            return
        seen.add(canonical)
        names.append(canonical)

    for name, polarity in (factor_states or {}).items():
        if polarity == FACTOR_STATE_AFFIRMED:
            _add(name)
    for name in matched_factors or ():
        _add(name, assume_affirmed=True)
    return tuple(names)


def touched_conditions(
    seeds: Sequence[str],
    ontology: RedFlagOntology,
) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for seed in seeds:
        for condition in conditions_for_factor(seed, ontology):
            if condition not in seen:
                seen.add(condition)
                out.append(condition)
    return tuple(out)


def eligible_neighbour_factors(
    factor_states: dict[str, str] | None,
    *,
    matched_factors: Iterable[str] | None = None,
    ontology: RedFlagOntology | None = None,
) -> tuple[str, ...]:
    """Askable, still-unasked factors one hop from a clinical-finding seed.

    Recorded polarities (affirmed, denied, or explicit unknown) are skipped;
    absent keys remain candidates. Non-askable mediators are dropped; their
    askable sources already sit on the same condition via mediated edge rows,
    so they remain candidates.
    """
    ont = ontology or load_ontology_for_profile()
    seeds = clinical_finding_seeds(
        factor_states, matched_factors, ontology=ont
    )
    if not seeds:
        return ()
    touched = set(touched_conditions(seeds, ont))
    seed_set = set(seeds)
    out: list[str] = []
    seen: set[str] = set()
    for condition in ont.conditions:
        if condition not in touched:
            continue
        for factor in ont.factors_by_condition.get(condition, ()):
            if factor in seen or factor in seed_set:
                continue
            seen.add(factor)
            if _recorded_polarity(factor_states, factor) is not None:
                continue
            spec = ont.get_factor_question_spec(factor)
            if spec is None or not spec.askable:
                continue
            out.append(factor)
    return tuple(out)


def remaining_floor_count(coverage: CoverageReport) -> int:
    return len(coverage.get("missing_slots") or [])


def floor_budget_exhausted(*, questions_asked: int, max_questions: int, remaining_floor: int) -> bool:
    """True when remaining turns would starve the floor if a non-floor ask ran."""
    if remaining_floor <= 0:
        return False
    turns_left = max_questions - questions_asked
    return turns_left <= remaining_floor


@dataclass(frozen=True)
class RankedCandidate:
    kind: Kind
    name: str
    tier: int
    topic: str
    reason: str
    symptom_id: str | None = None
    condition: str | None = None
    is_specific: bool = False
    multi_condition: bool = False
    matched_on_condition: int = 0
    ontology_index: int = 0
    slot_order: int = 0

    def sort_key(self, *, same_topic: bool) -> tuple:
        return (
            self.tier,
            0 if same_topic else 1,
            0 if self.is_specific else 1,
            0 if self.multi_condition else 1,
            -self.matched_on_condition,
            self.slot_order,
            self.ontology_index,
            self.name,
        )


def _slot_topic(slot: SlotName, symptom_id: str | None) -> str:
    if slot == "symptom_anchor":
        return "anchor"
    if slot in {"age", "sex"}:
        return "demographics"
    if slot == "comorbidities":
        return "comorbidities"
    return f"symptom:{symptom_id or ''}"


def _slot_order_index(slot: SlotName) -> int:
    if slot in TIER2_SLOT_ORDER:
        return TIER2_SLOT_ORDER.index(slot)
    if slot in TIER4_SLOT_ORDER:
        return TIER4_SLOT_ORDER.index(slot)
    return 99


def _slot_reason(slot: SlotName, *, symptom_id: str | None, tier: int) -> str:
    base = f"rank:t{tier}:{slot}"
    if symptom_id:
        return f"{base}:symptom={symptom_id}"
    return base


def slot_candidates(coverage: CoverageReport) -> list[RankedCandidate]:
    out: list[RankedCandidate] = []
    for missing in coverage.get("missing_slots") or []:
        slot = missing.get("slot")
        if slot not in SLOT_TIER:
            continue
        sid = missing.get("symptom_id")
        tier = SLOT_TIER[slot]
        out.append(
            RankedCandidate(
                kind="slot",
                name=slot,
                tier=tier,
                topic=_slot_topic(slot, sid),
                reason=_slot_reason(slot, symptom_id=sid, tier=tier),
                symptom_id=sid,
                slot_order=_slot_order_index(slot),
            )
        )
    return out


def factor_candidates(
    factors: Sequence[str],
    *,
    factor_states: dict[str, str] | None,
    ontology: RedFlagOntology,
    matched_factors: Iterable[str] | None = None,
    profile: TriageProfile | None = None,
) -> list[RankedCandidate]:
    seeds = clinical_finding_seeds(
        factor_states, matched_factors, ontology=ontology
    )
    touched = touched_conditions(seeds, ontology)
    matched_on: dict[str, int] = {condition: 0 for condition in touched}
    for seed in seeds:
        for condition in conditions_for_factor(seed, ontology):
            if condition in matched_on:
                matched_on[condition] += 1
    factor_index = {name: i for i, name in enumerate(ontology.all_factors)}
    out: list[RankedCandidate] = []
    for factor in factors:
        spec = ontology.get_factor_question_spec(factor)
        if spec is None or not spec.askable:
            continue
        conds = conditions_for_factor(factor, ontology)
        touched_for_factor = [c for c in conds if c in set(touched)]
        primary = best_condition_for_factor(
            factor, ontology, prefer=touched_for_factor, profile=profile
        )
        if primary is None:
            continue
        tier = min(
            (condition_tier(c, profile) for c in (touched_for_factor or conds)),
            default=TIER_MECHANICAL,
        )
        hits = max((matched_on.get(c, 0) for c in touched_for_factor), default=0)
        out.append(
            RankedCandidate(
                kind="factor",
                name=spec.factor,
                tier=tier,
                topic=f"condition:{primary}",
                reason=f"rank:t{tier}:{primary}:{spec.factor}",
                condition=primary,
                is_specific=ontology.factor_is_specific(spec.factor),
                multi_condition=len(touched_for_factor) >= 2,
                matched_on_condition=hits,
                        ontology_index=factor_index.get(spec.factor, len(factor_index)),
            )
        )
    return out


def apply_coherence_guard(
    ranked: Sequence[RankedCandidate],
    *,
    last_topic: str | None,
    last_tier: int | None,
) -> RankedCandidate | None:
    """Keep the incumbent topic unless the winner is a full tier better.

    Tier 1 time-critical factors always pre-empt.
    """
    if not ranked:
        return None
    winner = ranked[0]
    if not last_topic or last_tier is None:
        return winner
    if winner.topic == last_topic:
        return winner
    if winner.tier == TIER_TIME_CRITICAL:
        return winner
    if winner.tier <= last_tier - 1:
        return winner
    incumbents = [c for c in ranked if c.topic == last_topic]
    if incumbents:
        return incumbents[0]
    return winner


def rank_question_candidates(
    coverage: CoverageReport,
    factor_states: dict[str, str] | None,
    *,
    matched_factors: Iterable[str] | None = None,
    ontology: RedFlagOntology | None = None,
    last_topic: str | None = None,
    last_tier: int | None = None,
    floor_only: bool = False,
    profile: TriageProfile | None = None,
) -> list[RankedCandidate]:
    ont = ontology or load_ontology_for_profile(profile)
    slots = slot_candidates(coverage)
    factors: list[RankedCandidate] = []
    if not floor_only:
        names = eligible_neighbour_factors(
            factor_states, matched_factors=matched_factors, ontology=ont
        )
        factors = factor_candidates(
            names,
            factor_states=factor_states,
            ontology=ont,
            matched_factors=matched_factors,
            profile=profile,
        )
    pool = [*slots, *factors]
    pool.sort(key=lambda c: c.sort_key(same_topic=c.topic == last_topic))
    chosen = apply_coherence_guard(pool, last_topic=last_topic, last_tier=last_tier)
    if chosen is None:
        return []
    # Keep the chosen candidate first so callers can take pool[0] after guard.
    rest = [c for c in pool if c is not chosen]
    return [chosen, *rest]


def has_unknown_time_critical(
    factor_states: dict[str, str] | None,
    *,
    matched_factors: Iterable[str] | None = None,
    ontology: RedFlagOntology | None = None,
    profile: TriageProfile | None = None,
) -> bool:
    ont = ontology or load_ontology_for_profile(profile)
    critical = (profile or get_triage_profile()).time_critical_conditions
    for factor in eligible_neighbour_factors(
        factor_states, matched_factors=matched_factors, ontology=ont
    ):
        primary = best_condition_for_factor(factor, ont, profile=profile)
        if primary in critical:
            return True
        if any(c in critical for c in conditions_for_factor(factor, ont)):
            return True
    return False
