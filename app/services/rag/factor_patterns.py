"""Regex registry mapping checklist text to canonical graph Factor names."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.services.graphrag.neo4j_config import DEFAULT_INVENTORY_PATH

_WS = re.compile(r"\s+")


@dataclass
class FactorPattern:
    factor_name: str
    patterns: list[re.Pattern[str]] = field(default_factory=list)
    checklist_kinds: frozenset[str] = frozenset()
    checklist_labels: frozenset[str] = frozenset()
    priority: int = 0


_KIND_LABEL_FACTORS: dict[tuple[str, str], str] = {
    ("demographic", "age"): "Age over 50",
    ("comorbidity", "diabetes"): "Diabetes",
    ("comorbidity", "osteoporosis"): "Osteoporosis",
    ("comorbidity", "cancer"): "Previous cancer",
    ("severity", "symptom_severity"): "Severe pain",
    ("symptom_quality", "night_pain"): "Night pain",
    ("symptom_quality", "weight_loss"): "Unexplained weight loss",
    ("provocative", "weight_bearing"): "Pain weight-bearing",
    ("palliative", "rest"): "Constant pain",
}

_TEXT_ALIASES: dict[str, str] = {
    "feverish": "Fever",
    "high temperature": "Fever",
    "recent fall": "Recent trauma",
    "fall": "Recent trauma",
    "trauma": "Recent trauma",
    "bruise": "Bruising",
    "calf ache": "Calf pain",
    "leg swelling": "Calf swelling",
    "bladder": "Bladder dysfunction",
    "bowel": "Bowel dysfunction",
    "numbness saddle": "Saddle anaesthesia",
    "saddle anesthesia": "Saddle anaesthesia",
    "saddle anaesthesia": "Saddle anaesthesia",
    "weight bearing": "Pain weight-bearing",
    "night pain": "Night pain",
    "age over 50": "Age over 50",
    "over 50": "Age over 50",
    "over fifty": "Age over 50",
    "iv drug": "IV drug user",
    "immunosuppressed": "Immunosuppression",
    "immunosuppression": "Immunosuppression",
    "steroids": "Corticosteroids",
    "corticosteroid": "Corticosteroids",
}


def _norm(text: str) -> str:
    return _WS.sub(" ", text.casefold().strip())


def _age_implies_over_50(text: str) -> bool:
    for match in re.finditer(r"\b(\d{1,3})\b", text):
        try:
            age = int(match.group(1))
        except ValueError:
            continue
        if age >= 50:
            return True
    return any(token in _norm(text) for token in ("over 50", "over fifty", "elderly", "geriatric"))


# Word-boundary sex tokens (female before male: "female" contains "male", "woman" contains "man").
_FEMALE_SEX_RE = re.compile(
    r"\b(?:female|woman|women|gal|girl|lady|gentlewoman|f)\b",
    re.IGNORECASE,
)
_MALE_SEX_RE = re.compile(
    r"\b(?:male|man|men|guy|dude|lad|bloke|boy|gentleman|m)\b",
    re.IGNORECASE,
)


def _sex_factor(text: str) -> str | None:
    low = _norm(text)
    if _FEMALE_SEX_RE.search(low):
        return "Female sex"
    if _MALE_SEX_RE.search(low):
        return "Male sex"
    return None


@lru_cache(maxsize=1)
def load_factor_names(inventory_path: str) -> tuple[str, ...]:
    path = Path(inventory_path)
    if not path.is_file():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    factors = data.get("factors") or []
    return tuple(str(name) for name in factors)


def _name_pattern(factor_name: str) -> re.Pattern[str]:
    escaped = re.escape(factor_name)
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


@lru_cache(maxsize=1)
def build_factor_patterns(inventory_path: str) -> tuple[FactorPattern, ...]:
    factors = load_factor_names(inventory_path)
    factor_set = set(factors)
    patterns: list[FactorPattern] = []

    for kind_label, factor in _KIND_LABEL_FACTORS.items():
        if factor in factor_set:
            kind, label = kind_label
            patterns.append(
                FactorPattern(
                    factor_name=factor,
                    checklist_kinds=frozenset({kind}),
                    checklist_labels=frozenset({label}),
                    priority=10,
                )
            )

    alias_by_factor: dict[str, list[re.Pattern[str]]] = {}
    for alias, factor in _TEXT_ALIASES.items():
        if factor in factor_set:
            alias_by_factor.setdefault(factor, []).append(
                re.compile(re.escape(alias), re.IGNORECASE)
            )

    for factor in factors:
        pats = [_name_pattern(factor)]
        pats.extend(alias_by_factor.get(factor, []))
        patterns.append(FactorPattern(factor_name=factor, patterns=pats, priority=5))

    return tuple(patterns)


def known_chunk_ids(inventory_path: str | None = None) -> frozenset[str]:
    path = Path(inventory_path or DEFAULT_INVENTORY_PATH)
    if not path.is_file():
        return frozenset()
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks = data.get("chunk_ids") or data.get("chunks") or []
    return frozenset(str(c) for c in chunks)
