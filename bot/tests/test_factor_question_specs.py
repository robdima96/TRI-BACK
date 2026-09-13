"""v4 factors CSV loaders: askable specs, is_specific, inventory coverage."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.schemas import ChecklistItem
from app.services.agentic_graph_rag.ontology import (
    factor_is_specific,
    get_factor_question_spec,
    load_ontology,
)
from app.services.graphrag.csv_rows import FactorSheetError, load_factor_sheet
from app.services.rag.factor_matcher import (
    affirmed_factor_names,
    match_checklist_to_factors,
)


def test_ces_neighbourhood_includes_confirm_against_factors():
    ont = load_ontology()
    ces = ont.factors_by_condition["CES"]
    assert "Neuro sensory deficit" in ces
    assert "Neuro motor deficit" in ces
    assert "Saddle anaesthesia" in ces


def test_saddle_spec_from_v4_factors_csv():
    spec = get_factor_question_spec("Saddle anaesthesia")
    assert spec is not None
    assert spec.askable is True
    assert "groin" in spec.intent.lower() or "saddle" in spec.intent.lower()
    assert spec.fallback.endswith("?")
    assert "saddle numbness" in {s.casefold() for s in spec.synonyms}


def test_endothelial_injury_is_not_askable():
    spec = get_factor_question_spec("Endothelial injury")
    assert spec is not None
    assert spec.askable is False
    assert spec.fallback == ""


def test_hypercoagulability_not_askable_but_still_matches():
    spec = get_factor_question_spec("Hypercoagulability")
    assert spec is not None
    assert spec.askable is False
    matches = match_checklist_to_factors(
        [
            ChecklistItem(
                text="clotting disorder",
                kind="comorbidity",
                source="pattern",
                label="comorbidity",
            )
        ]
    )
    assert "Hypercoagulability" in affirmed_factor_names(matches)


def test_saddle_is_specific():
    assert factor_is_specific("Saddle anaesthesia") is True
    ont = load_ontology()
    assert ont.factor_is_specific("Saddle anaesthesia") is True
    assert ont.factor_is_specific("Neuro sensory deficit") is False


def test_missing_inventory_name_is_rejected(tmp_path: Path):
    path = tmp_path / "factors.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["source_nodes", "askable", "intent", "fallback", "synonyms"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_nodes": "Fever",
                "askable": "yes",
                "intent": "fever",
                "fallback": "Have you had a fever?",
                "synonyms": "feverish",
            }
        )
    with pytest.raises(FactorSheetError, match="no sheet row"):
        load_factor_sheet(path, ["Fever", "Saddle anaesthesia"])


def test_duplicate_factor_key_is_rejected(tmp_path: Path):
    path = tmp_path / "factors.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["source_nodes", "askable", "intent", "fallback", "synonyms"]
        )
        writer.writeheader()
        row = {
            "source_nodes": "Fever",
            "askable": "yes",
            "intent": "fever",
            "fallback": "Have you had a fever?",
            "synonyms": "feverish",
        }
        writer.writerow(row)
        writer.writerow(row)
    with pytest.raises(FactorSheetError, match="duplicate"):
        load_factor_sheet(path, ["Fever"])
