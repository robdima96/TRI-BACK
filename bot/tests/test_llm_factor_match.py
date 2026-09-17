"""Tests for LLM unmatched-factor cross-check (mocked generator)."""

from __future__ import annotations

import json

import pytest

from app.config import settings
from app.schemas import ChecklistItem
from app.services.graphrag.schemas import FactorMatch
from app.services.rag.factor_matcher import match_checklist_to_factors
from app.services.rag.llm_factor_match import (
    eligible_for_llm_match,
    llm_match_unmatched_factors,
)
from app.services.rag.factor_patterns import load_factor_names
from app.services.graphrag.neo4j_config import DEFAULT_INVENTORY_PATH


@pytest.fixture
def enable_llm_factor_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_factor_match", True)


def test_eligible_skips_gated_age_and_severity():
    age = FactorMatch(
        checklist_item={
            "text": "30",
            "kind": "demographic",
            "source": "pattern",
            "label": "age",
        },
        factor_name=None,
        match_method="none",
        match_score=0.0,
    )
    sev = FactorMatch(
        checklist_item={
            "text": "mild",
            "kind": "severity",
            "source": "pattern",
            "label": "symptom_severity",
        },
        factor_name=None,
        match_method="none",
        match_score=0.0,
    )
    assert eligible_for_llm_match(age) is False
    assert eligible_for_llm_match(sev) is False


def test_eligible_allows_unmatched_provocative():
    m = FactorMatch(
        checklist_item={
            "text": "can't use a chair for long",
            "kind": "provocative",
            "source": "slot_answer",
            "label": "provocative",
        },
        factor_name=None,
        match_method="none",
        match_score=0.0,
    )
    assert eligible_for_llm_match(m) is True


def test_llm_match_accepts_chair_paraphrase(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    factors = load_factor_names(str(DEFAULT_INVENTORY_PATH))
    if "Prolonged sitting aggravates" not in factors:
        pytest.skip("inventory lacks Prolonged sitting aggravates (need v2)")

    matches = [
        FactorMatch(
            checklist_item={
                "text": "can't use a chair for long",
                "kind": "provocative",
                "source": "test",
                "label": "provocative",
            },
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )
    ]

    def fake_generate(messages, **kwargs):
        return json.dumps(
            {
                "matches": [
                    {
                        "index": 1,
                        "factor_name": "Prolonged sitting aggravates",
                        "confidence": 0.91,
                        "reason": "chair intolerance implies sitting aggravates",
                    }
                ]
            }
        )

    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        fake_generate,
    )

    out = llm_match_unmatched_factors(matches, factors)
    assert out[0].factor_name == "Prolonged sitting aggravates"
    assert out[0].match_method == "llm_semantic"
    assert out[0].match_score >= 0.7


def test_llm_match_abstains_when_null(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    factors = load_factor_names(str(DEFAULT_INVENTORY_PATH))
    matches = [
        FactorMatch(
            checklist_item={
                "text": "back",
                "kind": "ner_entity",
                "source": "gliner",
                "label": "body part",
            },
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )
    ]

    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        lambda *a, **k: json.dumps(
            {
                "matches": [
                    {
                        "index": 1,
                        "factor_name": None,
                        "confidence": 0.0,
                        "reason": "body part only",
                    }
                ]
            }
        ),
    )

    out = llm_match_unmatched_factors(matches, factors)
    assert out[0].factor_name is None
    assert out[0].match_method == "none"


def test_llm_match_rejects_hallucinated_factor(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    factors = load_factor_names(str(DEFAULT_INVENTORY_PATH))
    matches = [
        FactorMatch(
            checklist_item={
                "text": "weird pain",
                "kind": "symptom",
                "source": "test",
                "label": "symptom",
            },
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )
    ]

    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        lambda *a, **k: json.dumps(
            {
                "matches": [
                    {
                        "index": 1,
                        "factor_name": "Totally Made Up Factor",
                        "confidence": 0.99,
                        "reason": "hallucination",
                    }
                ]
            }
        ),
    )

    out = llm_match_unmatched_factors(matches, factors)
    assert out[0].factor_name is None
    assert out[0].match_method == "none"


def test_llm_match_rejects_low_confidence(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    factors = load_factor_names(str(DEFAULT_INVENTORY_PATH))
    if "Osteoarthritis" not in factors:
        pytest.skip("inventory lacks Osteoarthritis")

    matches = [
        FactorMatch(
            checklist_item={
                "text": "arthritis",
                "kind": "comorbidity",
                "source": "test",
                "label": "comorbidity",
            },
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )
    ]

    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        lambda *a, **k: json.dumps(
            {
                "matches": [
                    {
                        "index": 1,
                        "factor_name": "Osteoarthritis",
                        "confidence": 0.4,
                        "reason": "maybe",
                    }
                ]
            }
        ),
    )

    out = llm_match_unmatched_factors(matches, factors)
    assert out[0].factor_name is None


def test_match_checklist_llm_path_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    """Chair paraphrase misses regex; LLM fill-in runs after deterministic pass."""
    factors = load_factor_names(str(DEFAULT_INVENTORY_PATH))
    if "Prolonged sitting aggravates" not in factors:
        pytest.skip("inventory lacks Prolonged sitting aggravates (need v2)")

    items = [
        ChecklistItem(
            text="can't use a chair for long",
            kind="provocative",
            source="test",
            label="provocative",
        )
    ]
    # Without LLM: should miss
    monkeypatch.setattr(settings, "llm_factor_match", False)
    deterministic = match_checklist_to_factors(items)
    assert deterministic[0].factor_name is None

    monkeypatch.setattr(settings, "llm_factor_match", True)
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        lambda *a, **k: json.dumps(
            {
                "matches": [
                    {
                        "index": 1,
                        "factor_name": "Prolonged sitting aggravates",
                        "confidence": 0.88,
                        "reason": "chair = sitting",
                    }
                ]
            }
        ),
    )
    filled = match_checklist_to_factors(items)
    assert filled[0].factor_name == "Prolonged sitting aggravates"
    assert filled[0].match_method == "llm_semantic"


def test_llm_disabled_is_noop(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "llm_factor_match", False)
    factors = ("Fever",)
    matches = [
        FactorMatch(
            checklist_item={
                "text": "feverish",
                "kind": "symptom",
                "source": "test",
                "label": "symptom",
            },
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )
    ]
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("LLM should not be called when flag is off")

    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        boom,
    )
    out = llm_match_unmatched_factors(matches, factors)
    assert called["n"] == 0
    assert out[0].factor_name is None


def test_young_age_not_sent_to_llm_even_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )

    def boom(*a, **k):
        raise AssertionError("gated age must not trigger LLM")

    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        boom,
    )
    items = [
        ChecklistItem(text="30", kind="demographic", source="pattern", label="age"),
    ]
    matches = match_checklist_to_factors(items)
    assert matches[0].factor_name is None


def test_llm_match_one_to_many_with_polarity(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    factors = load_factor_names(str(DEFAULT_INVENTORY_PATH))
    needed = ("Lumbar stiffness", "Movement-related pain")
    if any(name not in factors for name in needed):
        pytest.skip("inventory lacks stiffness / movement factors")

    matches = [
        FactorMatch(
            checklist_item={
                "text": "It's pretty stiff so I don't move it a lot",
                "kind": "symptom_quality",
                "source": "test",
                "label": "symptom_quality",
            },
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )
    ]

    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        lambda *a, **k: json.dumps(
            {
                "matches": [
                    {
                        "index": 1,
                        "factor_name": "Lumbar stiffness",
                        "polarity": "affirmed",
                        "confidence": 0.93,
                        "reason": "stiff",
                    },
                    {
                        "index": 1,
                        "factor_name": "Movement-related pain",
                        "polarity": "affirmed",
                        "confidence": 0.9,
                        "reason": "guards against moving",
                    },
                ]
            }
        ),
    )
    out = llm_match_unmatched_factors(matches, factors)
    names = {m.factor_name for m in [out[0], *()]}
    mention_names = {m.factor_name: m.polarity for m in out[0].mentions}
    assert out[0].factor_name in needed
    assert out[0].polarity == "affirmed"
    assert mention_names["Lumbar stiffness"] == "affirmed"
    assert mention_names["Movement-related pain"] == "affirmed"
    assert "Lumbar stiffness" in mention_names
    assert names | set(mention_names) >= set(needed)


def test_llm_match_rejects_palliative_onset(
    monkeypatch: pytest.MonkeyPatch,
    enable_llm_factor_match: None,
):
    factors = load_factor_names(str(DEFAULT_INVENTORY_PATH))
    if "Activity-related onset" not in factors:
        pytest.skip("inventory lacks Activity-related onset")

    matches = [
        FactorMatch(
            checklist_item={
                "text": "exercise",
                "kind": "palliative",
                "source": "test",
                "label": "palliative",
            },
            factor_name=None,
            match_method="none",
            match_score=0.0,
        )
    ]
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generator_model_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.services.rag.llm_factor_match.generate_from_messages",
        lambda *a, **k: json.dumps(
            {
                "matches": [
                    {
                        "index": 1,
                        "factor_name": "Activity-related onset",
                        "polarity": "affirmed",
                        "confidence": 0.95,
                        "reason": "exercise",
                    }
                ]
            }
        ),
    )
    out = llm_match_unmatched_factors(matches, factors)
    assert out[0].factor_name is None
    assert out[0].match_method == "none"
