"""OSCE LBP case cards: AgentClinic mapping + Hidden withheld from the patient."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "references" / "osce_lbp_schema.json"

# PatientSim-style persona (Kyung et al., NeurIPS 2025). Orthogonal to the stem.
# Values are the closed set on the OSCE card; the patient prompt must not invent extras.
PERSONALITY_VALUES = (
    "impatient",
    "overanxious",
    "distrustful",
    "overly_positive",
    "verbose",
    "neutral",
)
LANGUAGE_PROFICIENCY_VALUES = ("basic", "intermediate", "advanced")
MEDICAL_HISTORY_RECALL_VALUES = ("high_recall", "low_recall")
COGNITIVE_CONFUSION_VALUES = ("highly_confused", "normal")

PERSONA_ALLOWED: dict[str, frozenset[str]] = {
    "personality": frozenset(PERSONALITY_VALUES),
    "language_proficiency": frozenset(LANGUAGE_PROFICIENCY_VALUES),
    "medical_history_recall": frozenset(MEDICAL_HISTORY_RECALL_VALUES),
    "cognitive_confusion": frozenset(COGNITIVE_CONFUSION_VALUES),
}

DEFAULT_PERSONA: dict[str, str] = {
    "personality": "neutral",
    "language_proficiency": "advanced",
    "medical_history_recall": "high_recall",
    "cognitive_confusion": "normal",
}

# Hidden.reference_labels — clinician scoring family. Not the MedQA MCQ answer.
# Auto-screen preview families (lexicon GRID_FAMILIES) are a separate Stage 1–2 grid.
REFERENCE_LABEL_VALUES = (
    "mechanical",
    "CES",
    "fracture",
    "malignancy",
    "infection",
    "vascular",
)
REFERENCE_LABELS_ALLOWED = frozenset(REFERENCE_LABEL_VALUES)


def default_persona() -> dict[str, str]:
    return dict(DEFAULT_PERSONA)


def resolve_persona(persona: dict[str, str] | None = None) -> dict[str, str]:
    """Return a complete persona dict, or raise if a key/value is not in the closed set."""
    if persona is None:
        return default_persona()
    unknown_keys = set(persona) - set(PERSONA_ALLOWED)
    if unknown_keys:
        raise ValueError(
            f"persona has unknown keys {sorted(unknown_keys)}; "
            f"allowed: {sorted(PERSONA_ALLOWED)}"
        )
    out = default_persona()
    for key, value in persona.items():
        if value not in PERSONA_ALLOWED[key]:
            raise ValueError(
                f"persona.{key}={value!r} is not allowed; "
                f"use one of {sorted(PERSONA_ALLOWED[key])}"
            )
        out[key] = value
    return out


def resolve_reference_labels(labels: list[str] | None = None) -> list[str]:
    """Return Hidden.reference_labels, or raise if a value is not in the closed set.

    Empty means clinician has not assigned yet. Do not put a MedQA answer string here.
    """
    if not labels:
        return []
    out: list[str] = []
    for label in labels:
        if label not in REFERENCE_LABELS_ALLOWED:
            raise ValueError(
                f"reference_labels contains {label!r}; "
                f"use only {list(REFERENCE_LABEL_VALUES)}"
            )
        if label not in out:
            out.append(label)
    return out


def load_card(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def patient_actor_only(card: dict[str, Any]) -> dict[str, Any]:
    """The patient agent must never see Hidden or diagnosis labels."""
    actor = card.get("Patient_Actor")
    if not isinstance(actor, dict):
        raise ValueError("card missing Patient_Actor")
    return json.loads(json.dumps(actor))


def from_agentclinic_osce(
    osce: dict[str, Any],
    *,
    source_id: str,
    stem_hash: str,
    persona: dict[str, str] | None = None,
) -> dict[str, Any]:
    exam = osce.get("OSCE_Examination") or osce
    actor = exam.get("Patient_Actor") or {}
    symptoms = actor.get("Symptoms") or {}
    primary = symptoms.get("Primary_Symptom") or ""
    secondary = symptoms.get("Secondary_Symptoms") or []
    history = str(actor.get("History") or "")
    demo = str(actor.get("Demographics") or "")
    opening = _opening_from_history(history, demo)

    return {
        "case_id": f"lbp_osce_{stem_hash[:8]}",
        "source_corpus": "medqa_us",
        "source_id": source_id,
        "stem_hash": stem_hash,
        "Patient_Actor": {
            "demographics": demo,
            "opening_complaint": opening,
            "history": history,
            "symptoms": {"primary": primary, "secondary": secondary},
            "intake": {
                "duration": "not specified on source stem — treat as unknown if asked",
                "severity_0_10": None,
                "severity_note": "not specified on source stem — treat as unknown if asked",
                "quality": primary or "not specified",
                "provocative": "not specified on source stem — treat as unknown if asked",
                "palliative": "not specified on source stem — treat as unknown if asked",
                "comorbidities": str(actor.get("Past_Medical_History") or "not specified"),
            },
            "red_flag_self_report": _red_flags_from_text(history + " " + str(actor.get("Review_of_Systems") or "")),
            "past_medical_history": str(actor.get("Past_Medical_History") or ""),
            "social_history": str(actor.get("Social_History") or ""),
            "review_of_systems": str(actor.get("Review_of_Systems") or ""),
            "unknowns": [
                "imaging results",
                "laboratory results",
                "physical exam findings the patient would not know",
                "any fact not written on this card",
            ],
            "persona": resolve_persona(persona),
        },
        "Hidden": {
            "reference_disposition": "clinician to assign after review",
            "reference_labels": resolve_reference_labels(None),
            "must_elicit": ["duration", "severity", "what makes it worse/better"],
        },
    }


def from_medqa_stem(
    *,
    question: str,
    answer: str,
    source_id: str,
    stem_hash: str,
    persona: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Stub card from a raw MedQA stem. Clinician must rewrite lay opening + intake."""
    demo_m = re.search(
        r"(\d{1,3}[-\s]?(?:year|yr)[-\s]?old\s+(?:man|woman|male|female|boy|girl|gentleman|lady))",
        question,
        re.I,
    )
    demo = demo_m.group(1) if demo_m else "not specified"
    opening = _opening_from_history(question, demo)
    return {
        "case_id": f"lbp_osce_{stem_hash[:8]}",
        "source_corpus": "medqa_us",
        "source_id": source_id,
        "stem_hash": stem_hash,
        "conversion": "stub_from_stem_needs_clinician_rewrite",
        "Patient_Actor": {
            "demographics": demo,
            "opening_complaint": opening,
            "history": question,
            "symptoms": {"primary": "low back pain (from stem)", "secondary": []},
            "intake": {
                "duration": "not specified on source stem — treat as unknown if asked",
                "severity_0_10": None,
                "severity_note": "not specified on source stem — treat as unknown if asked",
                "quality": "not specified on source stem — treat as unknown if asked",
                "provocative": "not specified on source stem — treat as unknown if asked",
                "palliative": "not specified on source stem — treat as unknown if asked",
                "comorbidities": "not specified on source stem — treat as unknown if asked",
            },
            "red_flag_self_report": _red_flags_from_text(question),
            "past_medical_history": "not specified on source stem",
            "social_history": "not specified on source stem",
            "review_of_systems": "not specified on source stem",
            "unknowns": [
                "imaging results",
                "laboratory results",
                "physical exam findings the patient would not know",
                "any fact not written on this card",
            ],
            "persona": resolve_persona(persona),
        },
        "Hidden": {
            "reference_disposition": "clinician to assign after review",
            "reference_labels": resolve_reference_labels(None),
            "must_elicit": ["duration", "severity", "what makes it worse/better"],
        },
    }


def _opening_from_history(history: str, demo: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", history.strip())
    first = sentence[0] if sentence else history
    first = first.strip()
    if len(first) > 180:
        first = first[:177] + "..."
    # Avoid dumping demographics + full HPI as the first chat bubble.
    if demo and first.lower().startswith(demo.lower()[:20].lower()):
        rest = first[len(demo) :].lstrip(" .,:")
        if rest:
            return rest[0].upper() + rest[1:] if len(rest) > 1 else rest
    return first or "My lower back hurts."


def _red_flags_from_text(text: str) -> dict[str, str]:
    t = text.lower()

    def yn(pos: str, neg_patterns: list[str]) -> str:
        if any(n in t for n in neg_patterns):
            return "no"
        if pos in t:
            return "mentioned in stem — disclose only if asked"
        return "not specified — treat as unknown if asked"

    return {
        "trauma": yn("fall", ["denies"]) if "fall" in t or "trauma" in t else "not specified — treat as unknown if asked",
        "leg_weakness": yn("weak", ["denies weakness", "no weakness"]),
        "saddle_numbness": yn("saddle", ["denies", "no saddle"]),
        "bladder_bowel": yn("bladder", ["denies", "no change", "normal bowel"]),
        "fever": yn("fever", ["denies fever", "afebrile", "no fever"]),
        "unexplained_weight_loss": yn("weight loss", ["denies weight"]),
        "night_pain_waking": yn("night", ["denies night"]),
    }


def write_card(card: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
