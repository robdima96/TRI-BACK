"""LBP lexicon and staged filters for MedQA screening.

Every keep/drop decision returns a reason code so counts stay auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Stage 1 — high-recall LBP / lumbar / sciatica / red-flag / confounder terms.
# Order does not matter; we record which patterns hit.
LEXICON_PATTERNS: dict[str, str] = {
    "low_back": r"\b(low(?:er)?\s+back|lumbago)\b",
    "lumbar": r"\blumbar\b",
    "lumbosacral": r"\blumbosacral\b",
    "sciatica": r"\bsciatic(?:a|s)?\b",
    "radiculopathy": r"\bradiculopath\w*\b",
    "sacroiliac": r"\bsacroiliac\b",
    "sacrum": r"\bsacrum\b|\bsacral\b",
    "coccyx": r"\bcoccyx\b|\btailbone\b",
    "cauda_equina": r"\bcauda\s+equina\b",
    "saddle": r"\bsaddle\s+(?:anesth|numb|hypoest)",
    "spinal_stenosis": r"\bspinal\s+stenosis\b|\blumbar\s+stenosis\b",
    "neurogenic_claudication": r"\bneurogenic\s+claudication\b",
    "disc_herniation": r"\b(?:disc|disk)\s+herni\w*\b|\bherniated\s+(?:disc|disk)\b|\bnucleus\s+pulposus\b|\bHNP\b",
    "spondylolisthesis": r"\bspondylolisthesis\b",
    "spondylolysis": r"\bspondylolysis\b",
    "spondylosis": r"\bspondylosis\b",
    "ankylosing": r"\bankylosing\s+spondyl\w*\b",
    "sacroiliitis": r"\bsacroiliitis\b",
    "vertebral_fracture": r"\b(?:vertebral|compression|osteoporotic)\s+fracture\b",
    "epidural_abscess": r"\bepidural\s+abscess\b",
    "discitis": r"\b(?:discitis|diskitis)\b|\b(?:spinal|vertebral|lumbar|spine)\s+osteomyelitis\b",
    "spinal_met": r"\b(?:spinal|vertebral|spine)\s+metasta",
    "back_pain": r"\bback\s+pain\b",
    "confounder_aaa": r"\b(?:aortic\s+aneurysm|\bAAA\b)",
    "confounder_dvt": r"\b(?:DVT|deep\s+vein\s+thrombosis|deep\s+venous\s+thrombosis)\b",
    "confounder_abscess": (
        r"\b(?:IVDU|i\.?v\.?\s+drug|intravenous\s+drug|injection\s+drug).{0,80}"
        r"(?:abscess|discitis|osteomyelitis|back\s+pain|spine|spinal|lumbar)"
        r"|(?:psoas|iliopsoas|paraspinal|spinal\s+epidural)\s+abscess"
    ),
}

# Procedure-only hits that should not count as LBP presentations.
LUMBAR_PUNCTURE = re.compile(r"\blumbar\s+puncture\b", re.I)

AGE_RE = re.compile(
    r"\b(?:\d{1,3}[-\s]?(?:year|yr)[-\s]?old|\d{1,3}\s*(?:yo|y/o)\b|\dyears?\s+of\s+age)\b",
    re.I,
)
PRESENTATION_RE = re.compile(
    r"\b(?:presents?|presented|presenting|complain(?:s|ed|ing)?|history\s+of|comes?\s+to|brought\s+to|is\s+brought)\b",
    re.I,
)
CERVICAL_RE = re.compile(r"\b(?:cervical|neck\s+pain|cervicalgia)\b", re.I)
LUMBAR_REGION_RE = re.compile(
    r"\b(?:lumbar|low(?:er)?\s+back|sciatic|lumbosacral|cauda\s+equina|sacroiliac)\b",
    re.I,
)
RADIOLOGY_SPOT_RE = re.compile(
    r"\b(?:shown\s+(?:below|above|in\s+the\s+(?:figure|image|radiograph))|"
    r"identify\s+the\s+(?:radiographic\s+)?(?:sign|finding|structure)|"
    r"which\s+(?:image|radiograph|x-?ray|mri|ct)\s+(?:finding|shows))\b",
    re.I,
)

RED_FLAG_FAMILY_PATTERNS: dict[str, re.Pattern[str]] = {
    "ces": re.compile(r"cauda\s+equina|saddle\s+(?:anesth|numb)", re.I),
    "infection": re.compile(r"epidural\s+abscess|discitis|diskitis|osteomyelitis|iv\s+drug", re.I),
    "malignancy": re.compile(r"metasta|history\s+of\s+cancer|night\s+pain|weight\s+loss", re.I),
    "inflammatory": re.compile(r"ankylosing|sacroiliitis|hla[-\s]?b27|morning\s+stiffness", re.I),
    "trauma_fracture": re.compile(r"fracture|fell|fall|trauma|steroid", re.I),
    "confounder": re.compile(
        r"DVT|deep\s+vein\s+thrombosis|deep\s+venous\s+thrombosis|"
        r"IVDU|i\.?v\.?\s+drug|psoas\s+abscess|paraspinal\s+abscess|"
        r"aortic\s+aneurysm|\bAAA\b|pyelo|nephrolith",
        re.I,
    ),
    "mechanical": re.compile(
        r"herniat|sciatic|stenosis|lifting|mechanical|strain|spasm|radiculopath",
        re.I,
    ),
}

GRID_FAMILIES = (
    "mechanical",
    "trauma_fracture",
    "ces",
    "infection",
    "malignancy",
    "inflammatory",
    "confounder",
)


_COMPILED = {k: re.compile(p, re.I | re.S) for k, p in LEXICON_PATTERNS.items()}


@dataclass
class LexiconHit:
    matched: bool
    terms: list[str] = field(default_factory=list)


def haystack(*parts: str | None) -> str:
    return " ".join(p for p in parts if p)


def lexicon_hit(text: str) -> LexiconHit:
    terms = [name for name, rx in _COMPILED.items() if rx.search(text)]
    return LexiconHit(matched=bool(terms), terms=terms)


def is_lumbar_puncture_only(text: str, terms: list[str]) -> bool:
    """True when the only lumbar hit is the procedure 'lumbar puncture'."""
    if not LUMBAR_PUNCTURE.search(text):
        return False
    leftover = set(terms) - {"lumbar"}
    return not leftover


def is_vignette(text: str) -> tuple[bool, str | None]:
    has_age = bool(AGE_RE.search(text))
    has_pres = bool(PRESENTATION_RE.search(text))
    if has_age and has_pres:
        return True, None
    if not has_age:
        return False, "no_age_pattern"
    return False, "no_presentation_cue"


def is_cervical_only(text: str) -> bool:
    return bool(CERVICAL_RE.search(text)) and not bool(LUMBAR_REGION_RE.search(text))


def is_isolated_radiology(text: str) -> bool:
    """True for 'identify the sign' items that are not a patient vignette."""
    if not RADIOLOGY_SPOT_RE.search(text):
        return False
    ok, _ = is_vignette(text)
    return not ok


_DENIES_CLAUSE = re.compile(r"\bdenies\b[^.!?]{0,120}", re.I)


def preview_red_flag_family(text: str) -> str:
    """Provisional grid label for reporting. Clinician Stage 3 may override.

    Denial clauses (e.g. 'denies fever, weight loss') are stripped so they do not
    assign a red-flag family. MCQ options are not passed in (see MedQAItem.stem_text).
    """
    t = _DENIES_CLAUSE.sub(" ", text)
    for family in (
        "ces",
        "infection",
        "malignancy",
        "inflammatory",
        "trauma_fracture",
        "confounder",
        "mechanical",
    ):
        if RED_FLAG_FAMILY_PATTERNS[family].search(t):
            return family
    return "mechanical"


def token_count(text: str) -> int:
    return len(text.split())
