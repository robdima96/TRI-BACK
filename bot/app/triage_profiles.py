"""Session-level triage profile: assumed chief complaint + graph pack.

Today only ``low_back`` is registered. A later body-area picker can send
``triage_profile_id`` on the first chat turn to select another pack and
assumed symptom without changing the intake engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from app.services.graphrag.neo4j_config import (
    DEFAULT_CSV_PATH,
    DEFAULT_FACTORS_PATH,
    DEFAULT_INVENTORY_PATH,
)

DEFAULT_PROFILE_ID = "low_back"
PROFILE_SYMPTOM_SOURCE = "profile"

LOW_BACK_INTRO_MESSAGE = (
    "Hi, I'm TRI-BACK. I'm designed to help rule out any concerning patterns "
    "with your low back pain. This is not a medical diagnosis. If you "
    "think you have an emergency, seek urgent care right away. When you're ready, "
    "let's start with your age and the sex you were assigned at birth.",
)


@dataclass(frozen=True)
class TriageProfile:
    """Contract for one intake/graph pack (body area / condition family)."""

    id: str
    symptom_text: str
    intro_message: str
    graph_csv: Path
    graph_factors: Path
    graph_inventory: Path
    time_critical_conditions: tuple[str, ...]
    other_high_acuity_conditions: tuple[str, ...]
    mechanical_condition: str
    preferred_body_parts: tuple[str, ...]

    @property
    def assumes_symptom(self) -> bool:
        return bool(self.symptom_text.strip())


def _low_back_profile() -> TriageProfile:
    return TriageProfile(
        id=DEFAULT_PROFILE_ID,
        symptom_text="low back pain",
        intro_message=LOW_BACK_INTRO_MESSAGE,
        graph_csv=DEFAULT_CSV_PATH,
        graph_factors=DEFAULT_FACTORS_PATH,
        graph_inventory=DEFAULT_INVENTORY_PATH,
        time_critical_conditions=("CES", "AAA", "DVT"),
        other_high_acuity_conditions=("Fracture", "Malignancy", "Infection"),
        mechanical_condition="Non-specific Mechanical Cause",
        preferred_body_parts=("low back", "lower back", "lumbar", "spine", "back"),
    )


_REGISTRY: dict[str, TriageProfile] = {
    DEFAULT_PROFILE_ID: _low_back_profile(),
}


def get_triage_profile(profile_id: str | None = None) -> TriageProfile:
    """Resolve a registered profile; unknown or empty ids fall back to low_back."""
    key = (profile_id or "").strip() or DEFAULT_PROFILE_ID
    return _REGISTRY.get(key) or _REGISTRY[DEFAULT_PROFILE_ID]


def profile_from_state(state: Mapping[str, Any] | None) -> TriageProfile:
    return get_triage_profile((state or {}).get("triage_profile_id"))


def bind_triage_profile(state: MutableMapping[str, Any]) -> TriageProfile:
    """Stamp ``triage_profile_id`` on first turn; later turns keep the stamp."""
    existing = str(state.get("triage_profile_id") or "").strip()
    if existing:
        profile = get_triage_profile(existing)
        state["triage_profile_id"] = profile.id
        return profile
    requested = str(state.get("requested_triage_profile_id") or "").strip()
    profile = get_triage_profile(requested or DEFAULT_PROFILE_ID)
    state["triage_profile_id"] = profile.id
    return profile


def _is_symptom_row(row: Mapping[str, Any]) -> bool:
    return (
        row.get("kind") == "ner_entity"
        and str(row.get("label") or "").casefold() == "symptom"
    )


def _has_profile_symptom_seed(checklist: list[Mapping[str, Any]]) -> bool:
    return any(
        _is_symptom_row(row) and str(row.get("source") or "") == PROFILE_SYMPTOM_SOURCE
        for row in checklist
    )


def profile_symptom_seed_row(profile: TriageProfile) -> dict[str, Any]:
    """Checklist row that satisfies ``symptom_anchor`` from the session profile."""
    return {
        "text": profile.symptom_text,
        "kind": "ner_entity",
        "source": PROFILE_SYMPTOM_SOURCE,
        "label": "symptom",
        "confirmed": True,
    }


def seed_profile_symptom(state: MutableMapping[str, Any]) -> None:
    """Ensure the assumed chief-complaint row exists when the profile has one."""
    profile = get_triage_profile(state.get("triage_profile_id"))
    if not profile.assumes_symptom:
        return
    checklist = list(state.get("clinical_checklist") or [])
    if _has_profile_symptom_seed(checklist):
        return
    from app.orchestrator.checklist import ensure_row_identity

    checklist.append(ensure_row_identity(profile_symptom_seed_row(profile)))
    state["clinical_checklist"] = checklist


def load_ontology_for_profile(profile: TriageProfile | None = None):
    """Load (cached) ontology for the profile pack paths."""
    from app.services.agentic_graph_rag.ontology import load_ontology

    p = profile or get_triage_profile()
    return load_ontology(
        csv_path=p.graph_csv,
        factors_path=p.graph_factors,
        inventory_path=p.graph_inventory,
    )


def graph_client_for_profile(profile: TriageProfile | None = None):
    """Local CSV graph client keyed by the profile edges path."""
    from app.services.graphrag.local_graph import get_graph_client

    p = profile or get_triage_profile()
    return get_graph_client(csv_path=p.graph_csv)
