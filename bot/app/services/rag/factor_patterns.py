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
    # Age and severity are intentionally NOT here: they require text predicates
    # (_age_implies_over_50 / _severity_implies_severe) so "30" or "mild" cannot
    # blindly map to "Age over 50" / "Severe pain".
    ("comorbidity", "diabetes"): "Diabetes",
    ("comorbidity", "osteoporosis"): "Osteoporosis",
    ("comorbidity", "cancer"): "Previous cancer",
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
    "fell": "Recent trauma",
    "fallen": "Recent trauma",
    "falling": "Recent trauma",
    "fell off": "Recent trauma",
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
    # Non-specific mechanical factors 
    "movement related pain": "Movement-related pain",
    "pain with movement": "Movement-related pain",
    "pain with bending": "Movement-related pain",
    "worse with movement": "Movement-related pain",
    "changes with activity": "Movement-related pain",
    "mechanical pain": "Movement-related pain",
    "pain relieved by rest": "Pain relieved by rest",
    "eases with rest": "Pain relieved by rest",
    "better with rest": "Pain relieved by rest",
    "improves with rest": "Pain relieved by rest",
    "relieved by rest": "Pain relieved by rest",
    "rest helps": "Pain relieved by rest",
    "activity related onset": "Activity-related onset",
    "started after lifting": "Activity-related onset",
    "after lifting": "Activity-related onset",
    "after bending": "Activity-related onset",
    "after twisting": "Activity-related onset",
    "came on with activity": "Activity-related onset",
    "onset after activity": "Activity-related onset",
    "mechanical loading": "Mechanical loading",
    "load sensitive": "Mechanical loading",
    "load-sensitive": "Mechanical loading",
    "prior similar episodes": "Prior similar episodes",
    "previous episodes": "Prior similar episodes",
    "had this before": "Prior similar episodes",
    "recurrent back pain": "Prior similar episodes",
    "similar episode before": "Prior similar episodes",
    "lumbar stiffness": "Lumbar stiffness",
    "stiff back": "Lumbar stiffness",
    "stiffness in back": "Lumbar stiffness",
    "limited lumbar motion": "Lumbar stiffness",
    "reduced range of motion": "Lumbar stiffness",
    "fluctuating pain": "Fluctuating pain",
    "comes and goes": "Fluctuating pain",
    "waxing and waning": "Fluctuating pain",
    "varies through the day": "Fluctuating pain",
    "pain fluctuates": "Fluctuating pain",
    "improves with conservative care": "Improves with conservative care",
    "better with physio": "Improves with conservative care",
    "improving with physiotherapy": "Improves with conservative care",
    "responding to conservative": "Improves with conservative care",
    "getting better with rest and activity": "Improves with conservative care",
    "prolonged sitting aggravates": "Prolonged sitting aggravates",
    "worse with sitting": "Prolonged sitting aggravates",
    "sitting makes it worse": "Prolonged sitting aggravates",
    "pain after sitting": "Prolonged sitting aggravates",
    "sitting intolerance": "Prolonged sitting aggravates",
    "hard to sit": "Prolonged sitting aggravates",
    "whenever i sit": "Prolonged sitting aggravates",
    "when i sit": "Prolonged sitting aggravates",
    "i sit": "Prolonged sitting aggravates",
    "sit or lay": "Prolonged sitting aggravates",
    "sit or lie": "Prolonged sitting aggravates",
    "sitting": "Prolonged sitting aggravates",
    "position change relief": "Position change relief",
    "better with position change": "Position change relief",
    "eases when i change position": "Position change relief",
    "relieved by changing position": "Position change relief",
    "changing position": "Position change relief",
    "change position": "Position change relief",
    "change of position": "Position change relief",
    "position helps": "Position change relief",
    "changing positions": "Position change relief",
    "stretching seems to help": "Improves with conservative care",
    "stretching helps": "Improves with conservative care",
    "helps with stretching": "Improves with conservative care",
    "heavy lifting": "Heavy lifting",
    "lifting heavy": "Heavy lifting",
    "heavy loads": "Heavy lifting",
}

# Descriptive terms that imply severe (not mild/moderate).
_SEVERE_WORD_RE = re.compile(
    r"\b("
    r"severe|severely|excruciating|unbearable|debilitating|agoni[sz]ing|"
    r"intense|worst"
    r")\b",
    re.IGNORECASE,
)
_MILD_OR_MODERATE_RE = re.compile(
    r"\b(mild|slight|slightly|minimal|moderate|mod\.?)\b",
    re.IGNORECASE,
)
_PAIN_SCALE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:/\s*10|out\s+of\s+10)\b",
    re.IGNORECASE,
)
_BARE_SCORE_RE = re.compile(r"^\s*(\d{1,2})\s*$")


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
    return any(
        token in _norm(text) for token in ("over 50", "over fifty", "elderly", "geriatric")
    )


def _severity_implies_severe(text: str) -> bool:
    """True only when text implies severe pain (numeric ≥7 or severe-class words)."""
    raw = (text or "").strip()
    if not raw:
        return False
    has_severe_word = bool(_SEVERE_WORD_RE.search(raw))
    bare = _BARE_SCORE_RE.match(raw)
    if bare:
        try:
            score = int(bare.group(1))
        except ValueError:
            score = -1
        if 0 <= score <= 10:
            return score >= 7
    for match in _PAIN_SCALE_RE.finditer(raw):
        try:
            score = int(match.group(1))
        except ValueError:
            continue
        if 0 <= score <= 10:
            return score >= 7
    if has_severe_word:
        return True
    if _MILD_OR_MODERATE_RE.search(raw):
        return False
    return False


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


def _alias_pattern(alias: str) -> re.Pattern[str]:
    """Compile checklist aliases; word-bound single tokens to avoid substring hits."""
    escaped = re.escape(alias)
    if " " in alias:
        return re.compile(escaped, re.IGNORECASE)
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
            alias_by_factor.setdefault(factor, []).append(_alias_pattern(alias))

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
