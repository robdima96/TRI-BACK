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
    # Bare "bladder"/"bowel"/"calf"/"leg" are compiled as cue-cooccurrence
    # patterns below — they must not match a denial that merely echoes the organ.
    "numbness saddle": "Saddle anaesthesia",
    "saddle numbness": "Saddle anaesthesia",
    "numbness in the saddle": "Saddle anaesthesia",
    "saddle area": "Saddle anaesthesia",
    "saddle anesthesia": "Saddle anaesthesia",
    "saddle anaesthesia": "Saddle anaesthesia",
    "weight loss": "Unexplained weight loss",
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
    "sit or lay": "Prolonged sitting aggravates",
    "sit or lie": "Prolonged sitting aggravates",
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
    # Colloquial / clinical synonyms for inventory Factors that previously
    # matched only on the canonical name. Prefer phrases over bare tokens
    # except where GliNER often extracts a single body-part span (stomach/belly).
    "stomach": "Abdominal pain",
    "belly": "Abdominal pain",
    "abdomen": "Abdominal pain",
    "stomach pain": "Abdominal pain",
    "belly pain": "Abdominal pain",
    "stomach ache": "Abdominal pain",
    "belly ache": "Abdominal pain",
    "stomach hurts": "Abdominal pain",
    "belly hurts": "Abdominal pain",
    "abdomen hurts": "Abdominal pain",
    "stomach really hurts": "Abdominal pain",
    "belly really hurts": "Abdominal pain",
    "pain in my stomach": "Abdominal pain",
    "pain in my belly": "Abdominal pain",
    "pain in my abdomen": "Abdominal pain",
    "pain in the stomach": "Abdominal pain",
    "pain in the belly": "Abdominal pain",
    "flank pain": "Abdominal pain",
    "heavy drinking": "Alcohol",
    "alcoholic": "Alcohol",
    "alcohol use": "Alcohol",
    "drink heavily": "Alcohol",
    "drink a lot": "Alcohol",
    "both legs weak": "Bilat neuro motor deficit",
    "weakness in both legs": "Bilat neuro motor deficit",
    "bilateral leg weakness": "Bilat neuro motor deficit",
    "bilateral weakness": "Bilat neuro motor deficit",
    "both legs numb": "Bilat neuro sensory deficit",
    "numbness in both legs": "Bilat neuro sensory deficit",
    "bilateral numbness": "Bilat neuro sensory deficit",
    "bilateral sensory": "Bilat neuro sensory deficit",
    "red calf": "Calf redness",
    "calf is red": "Calf redness",
    "red and swollen calf": "Calf redness",
    "erythema calf": "Calf redness",
    "heart disease": "Cardiovascular disease",
    "heart problems": "Cardiovascular disease",
    "blocked arteries": "Cardiovascular disease",
    "coronary artery": "Cardiovascular disease",
    "vascular disease": "Cardiovascular disease",
    "cad": "Cardiovascular disease",
    "pvd": "Cardiovascular disease",
    "rigors": "Chills",
    "shivering": "Chills",
    "shaking chills": "Chills",
    "feeling shivery": "Chills",
    "central line": "Endothelial injury",
    "picc line": "Endothelial injury",
    "vein injury": "Endothelial injury",
    "injury to the vein": "Endothelial injury",
    "catheter in the vein": "Endothelial injury",
    "family history of aneurysm": "Family history of AAA",
    "aneurysm in the family": "Family history of AAA",
    "aneurysm runs in": "Family history of AAA",
    "parent had an aneurysm": "Family history of AAA",
    "relative with aneurysm": "Family history of AAA",
    "dad had an aneurysm": "Family history of AAA",
    "mom had an aneurysm": "Family history of AAA",
    "clotting disorder": "Hypercoagulability",
    "blood clots easily": "Hypercoagulability",
    "thrombophilia": "Hypercoagulability",
    "factor v": "Hypercoagulability",
    "thick blood": "Hypercoagulability",
    "high blood pressure": "Hypertension",
    "high bp": "Hypertension",
    "elevated bp": "Hypertension",
    "htn": "Hypertension",
    "leg weakness": "Neuro motor deficit",
    "legs feel weak": "Neuro motor deficit",
    "weak legs": "Neuro motor deficit",
    "legs are weak": "Neuro motor deficit",
    "foot drop": "Neuro motor deficit",
    "motor deficit": "Neuro motor deficit",
    "numbness in my leg": "Neuro sensory deficit",
    "numbness in the leg": "Neuro sensory deficit",
    "tingling down my leg": "Neuro sensory deficit",
    "pins and needles in my leg": "Neuro sensory deficit",
    "leg is numb": "Neuro sensory deficit",
    "sensory loss": "Neuro sensory deficit",
    "sweating at night": "Night sweats",
    "sweats at night": "Night sweats",
    "night sweat": "Night sweats",
    "wake up sweaty": "Night sweats",
    "waking up sweaty": "Night sweats",
    "drenching sweats": "Night sweats",
    "malnutrition": "Nutrient Deficiency",
    "poor nutrition": "Nutrient Deficiency",
    "not eating well": "Nutrient Deficiency",
    "eating disorder": "Nutrient Deficiency",
    "oa": "Osteoarthritis",
    "degenerative joint": "Osteoarthritis",
    "degenerative arthritis": "Osteoarthritis",
    "tender to touch": "Point tenderness",
    "tender to press": "Point tenderness",
    "sore to touch": "Point tenderness",
    "localized tenderness": "Point tenderness",
    "bone tenderness": "Point tenderness",
    "tender over the spine": "Point tenderness",
    "prior dvt": "Previous DVT",
    "history of dvt": "Previous DVT",
    "previous pe": "Previous DVT",
    "prior pe": "Previous DVT",
    "pulmonary embolism": "Previous DVT",
    "blood clot before": "Previous DVT",
    "had a clot": "Previous DVT",
    "clot in my leg": "Previous DVT",
    "bed rest": "Prolonged bed rest",
    "been in bed": "Prolonged bed rest",
    "stuck in bed": "Prolonged bed rest",
    "prolonged immobility": "Prolonged bed rest",
    "had surgery": "Recent surgery",
    "recent operation": "Recent surgery",
    "after my operation": "Recent surgery",
    "post-operative": "Recent surgery",
    "post operative": "Recent surgery",
    "just had surgery": "Recent surgery",
    "pain not improving": "Refractory pain",
    "pain not getting better": "Refractory pain",
    "physio did not help": "Refractory pain",
    "physio didn't help": "Refractory pain",
    "failed conservative": "Refractory pain",
    "not responding to treatment": "Refractory pain",
    "ra": "Rheumatoid arthritis",
    "rheumatoid": "Rheumatoid arthritis",
    "inflammatory arthritis": "Rheumatoid arthritis",
    "smoker": "Smoking",
    "i smoke": "Smoking",
    "cigarettes": "Smoking",
    "tobacco": "Smoking",
    "pack a day": "Smoking",
    "not moving much": "Venous stasis",
    "long haul flight": "Venous stasis",
    "long flight": "Venous stasis",
    "long car ride": "Venous stasis",
    "reduced mobility": "Venous stasis",
    "vitamin d": "Vitamin Deficiency",
    "low vitamin d": "Vitamin Deficiency",
    "vitamin d deficiency": "Vitamin Deficiency",
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
_SHORT_SCORE_RE = re.compile(r"\b(10|[0-9])\b")


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


def pain_score_0_to_10(text: str) -> int | None:
    """Best 0–10 pain score in ``text``, or None when no score is present.

    Short replies such as ``its like a 6`` count; longer narratives only count
    explicit ``n/10`` (or ``n out of 10``) so an age like 52 is not a severity.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    scores: list[int] = []
    bare = _BARE_SCORE_RE.match(raw)
    if bare:
        try:
            n = int(bare.group(1))
        except ValueError:
            n = -1
        if 0 <= n <= 10:
            scores.append(n)
    for match in _PAIN_SCALE_RE.finditer(raw):
        try:
            n = int(match.group(1))
        except ValueError:
            continue
        if 0 <= n <= 10:
            scores.append(n)
    if not scores and len(raw.split()) <= 8:
        for match in _SHORT_SCORE_RE.finditer(raw):
            try:
                n = int(match.group(1))
            except ValueError:
                continue
            if 0 <= n <= 10:
                scores.append(n)
    if not scores:
        return None
    return max(scores)


def _severity_implies_severe(text: str) -> bool:
    """True only when text implies severe pain (numeric ≥7 or severe-class words)."""
    raw = (text or "").strip()
    if not raw:
        return False
    score = pain_score_0_to_10(raw)
    if score is not None:
        return score >= 7
    if _SEVERE_WORD_RE.search(raw):
        return True
    if _MILD_OR_MODERATE_RE.search(raw):
        return False
    return False


def _severity_implies_not_severe(text: str) -> bool:
    """True when text is a 0–6 score or mild/moderate wording (not unknown)."""
    raw = (text or "").strip()
    if not raw:
        return False
    score = pain_score_0_to_10(raw)
    if score is not None:
        return score < 7
    return bool(_MILD_OR_MODERATE_RE.search(raw)) and not _SEVERE_WORD_RE.search(raw)


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


# Organ / region tokens that only map to a Factor when a symptom cue is nearby.
_DYSFUNCTION_CUE = (
    r"(?:problem(?:s)?|issue(?:s)?|incontinence|retention|control|"
    r"accident(?:s)?|leak(?:age|ing|s)?|trouble|dysfunction|"
    r"difficult(?:y|ies)?|can(?:not|'t)|urgency|incontinent|"
    r"dribbl(?:e|ing)|constipat(?:ed|ion)|fecal|stool|urine|urinary)"
)
_SADDLE_CUE = (
    r"(?:numb(?:ness)?|anaesth(?:esia)?|anesthes(?:ia)?|area|"
    r"dead|sensation|genitals?|perine(?:um|al)|wiping)"
)
_CALF_PAIN_CUE = r"(?:pain|ache(?:s|ing)?)"
_CALF_SWELL_CUE = r"(?:swell(?:ing|ed)?|swollen)"
_COOCCUR_GAP = 48

# (anchor token, factor, cue regex) — both orders, bounded gap.
_COOCCUR_ALIASES: tuple[tuple[str, str, str], ...] = (
    ("bladder", "Bladder dysfunction", _DYSFUNCTION_CUE),
    ("bowel", "Bowel dysfunction", _DYSFUNCTION_CUE),
    ("saddle", "Saddle anaesthesia", _SADDLE_CUE),
    ("calf", "Calf pain", _CALF_PAIN_CUE),
    ("calf", "Calf swelling", _CALF_SWELL_CUE),
    ("leg", "Calf swelling", _CALF_SWELL_CUE),
)


def _cooccur_pattern(anchor: str, cue: str) -> re.Pattern[str]:
    """Anchor token and cue within a short window (either order)."""
    a = re.escape(anchor)
    gap = rf".{{0,{_COOCCUR_GAP}}}"
    return re.compile(
        rf"\b{a}\b{gap}(?:{cue})|(?:{cue}){gap}\b{a}\b",
        re.IGNORECASE,
    )


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
    for anchor, factor, cue in _COOCCUR_ALIASES:
        if factor in factor_set:
            alias_by_factor.setdefault(factor, []).append(_cooccur_pattern(anchor, cue))

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
