"""Clinical NLP for one user turn: regex patterns, safety phrases, GliNER spans, checklist.

Extraction layers: pattern rules and ``safety_phrase`` substring matching
(:mod:`app.services.policy`), plus zero-shot span NER via GliNER-BioMed
(:mod:`app.services.gliner_ner`, ``DIGIMSK_LOAD_NER``).

RAG query embeddings use ``settings.encoder_model_dir`` (Clinical_sBERT via
``sentence_transformers`` by default; see ``DIGIMSK_RAG_EMBEDDING_BACKEND``).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import ChecklistItem, ClinicalChecklist, EncoderEntity, EncoderOutput

_log = logging.getLogger(__name__)

# --- Pattern extraction (durations, comorbidities, severity, quality, provocative vs palliative) ---

_COMORBIDITY = re.compile(
    r"\b("
    r"diabetes|t2dm|t1dm|hypertension|htn|"
    r"asthma|copd|osteoarthritis|oa|obesity|"
    r"depression|anxiety|fibromyalgia"
    r")\b",
    re.I, # case insensitive
)

_DURATION = re.compile(
    r"(?:\bfor\b\s*)?(\d{1,3})\s*(?:day|week|month)s?\b|"
    r"(\d{1,3})\s*(?:year|yr)s?(?!\s+old)\b|"
    r"\b(chronic|acute|lifelong|since childhood)\b|"
    r"\b(yesterday|today|last\s+night|this\s+morning)\b|"
    r"\b(\d{1,3})\s+days?\s+ago\b",
    re.I,
)

_AGE_TRIGGERS = re.compile(
    r"\b(?:age|patient\s+age|dob|date\s+of\s+birth|years?\s+old)\b"
    r"|(?:\bi\s+am|\bi'm)\s+(?:a\s+)?\d{1,3}\b",
    re.I,
)

_AGE_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(\d{1,3})\s*years?\s+old\b", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:year|yr)s?\s+old\b", re.I),
    re.compile(r"\b(?:age|patient\s+age)\s*(?:is|:)?\s*(\d{1,3})\b", re.I),
    re.compile(
        r"\b(?:i\s+am|i'm)\s+(?:a\s+)?(\d{1,3})\s*(?:year|yr)s?\s+old\b",
        re.I,
    ),
    re.compile(
        r"\b(?:i\s+am|i'm)\s+(?:a\s+)?(\d{1,3})\b(?!\s*(?:year|yr)s?\s+old\b)",
        re.I,
    ),
    re.compile(
        r"\b(?:dob|date\s+of\s+birth)\s*(?:is|:)?\s*"
        r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})\b",
        re.I,
    ),
)

# Colloquial and clinical sex tokens; normalized to male/female in checklist rows.
_SEX_MALE_TOKEN = r"(?:male|man|guy|dude|lad|bloke|boy|gentleman)"
_SEX_FEMALE_TOKEN = r"(?:female|woman|gal|girl|lady|gentlewoman)"
_SEX_VALUE_WORDS = rf"(?:{_SEX_MALE_TOKEN}|{_SEX_FEMALE_TOKEN})"

_SEX_CANONICAL: dict[str, str] = {
    "male": "male",
    "man": "male",
    "guy": "male",
    "dude": "male",
    "lad": "male",
    "bloke": "male",
    "boy": "male",
    "gentleman": "male",
    "m": "male",
    "female": "female",
    "woman": "female",
    "gal": "female",
    "girl": "female",
    "lady": "female",
    "gentlewoman": "female",
    "f": "female",
    "non-binary": "non-binary",
    "non binary": "non-binary",
    "nb": "non-binary",
}


def _canonical_sex_text(raw: str) -> str:
    """Map matched sex token or phrase to canonical male/female (etc.) for storage."""
    token = raw.strip()
    if not token:
        return ""
    low = token.casefold()
    if low in _SEX_CANONICAL:
        return _SEX_CANONICAL[low]
    m = re.search(rf"\b({_SEX_VALUE_WORDS})\b", token, re.I)
    if m:
        return _SEX_CANONICAL.get(m.group(1).casefold(), m.group(1).lower())
    return token


_SEX_TRIGGERS = re.compile(
    r"\b(?:sex|gender|biological\s+sex|patient\s+sex)\b",
    re.I,
)

# Optional words between "year old" and sex (e.g. "20 year old avid male sportsman").
_SEX_OLD_TO_VALUE_GAP = r"(?:\w+\s+){0,3}"

_SEX_STANDALONE_HINT = re.compile(
    rf"\b(?:i\s+am|i'm)\s+(?:a\s+)?{_SEX_VALUE_WORDS}\b"
    rf"|\b(?:year|yr)s?\s+old\s+{_SEX_OLD_TO_VALUE_GAP}{_SEX_VALUE_WORDS}\b"
    rf"|\b(?:i\s+am|i'm)\s+(?:a\s+)?\d{{1,3}}\s*(?:year|yr)s?\s+old\s+"
    rf"{_SEX_OLD_TO_VALUE_GAP}{_SEX_VALUE_WORDS}\b",
    re.I,
)

_SEX_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:sex|gender|biological\s+sex|patient\s+sex)\s*(?:is|:)?\s*"
        rf"({_SEX_MALE_TOKEN}|{_SEX_FEMALE_TOKEN}|non[- ]?binary|nb|m|f)\b",
        re.I,
    ),
    re.compile(
        rf"\b(?:i\s+am|i'm)\s+(?:a\s+)?({_SEX_VALUE_WORDS})\b",
        re.I,
    ),
    re.compile(
        rf"\b(\d{{1,3}})\s*(?:year|yr)s?\s+old\s+{_SEX_OLD_TO_VALUE_GAP}"
        rf"({_SEX_MALE_TOKEN}|{_SEX_FEMALE_TOKEN})\b",
        re.I,
    ),
    re.compile(
        rf"\b(?:i\s+am|i'm)\s+(?:a\s+)?(\d{{1,3}})\s*(?:year|yr)s?\s+old\s+"
        rf"{_SEX_OLD_TO_VALUE_GAP}({_SEX_MALE_TOKEN}|{_SEX_FEMALE_TOKEN})\b",
        re.I,
    ),
)

# Numeric pain ratings on a 0–10 scale (e.g. 7/10, 7 out of 10).
_PAIN_SCALE_NUMERIC = re.compile(
    r"\b(\d{1,2})\s*(?:/\s*10|out\s+of\s+10)\b",
    re.I,
)

# Descriptive severity words (scale ratings handled separately).
_DESCRIPTIVE_SEVERITY = re.compile(
    r"\b("
    r"mild(?!\s+bruising)|moderate|mod\.?|severe|slight|slightly|minimal|"
    r"intense|excruciating|debilitating|marked|significant|"
    r"very\s+painful|quite\s+bad|unbearable|worst\s+\d"
    r")\b",
    re.I,
)

_QUALITY = re.compile(
    r"\b("
    r"sharp|dull|achy|aching|ache|throb|throbbing|burning|stabbing|"
    r"shooting|radiating|radiates|spread(?:ing)?|tingling|numb(?:ness)?|"
    r"pins\s+and\s+needles|deep|tight|tightness|stiff|stiffness|heavy|catching"
    r")\b",
    re.I,
)

_PROVOC = re.compile(
    r"\b("
    r"worse\s+with|worse\s+when|aggravated\s+by|flares?\s+(?:up\s+)?when|"
    r"gets\s+worse\s+(?:with|when|after)|"
    r"worse\s+at\s+night|worse\s+in\s+the\s+morning|"
    r"worse\s+when\s+(?:sitting|standing|walking|bending|lifting|twisting|running)|"
    r"worse\s+with\s+(?:sitting|standing|walking|bending|lifting|twisting|movement|activity)|"
    r"pain\s+with\s+movement|pain\s+at\s+rest|"
    r"after\s+(?:activity|exercise|sitting)|"
    r"first\s+thing\s+(?:in\s+the\s+)?morning|during\s+the\s+day|"
    r"unable\s+to\s+(?:stand|walk|sit|sleep)|"
    r"triggered\s+by|provoked\s+by|brought\s+on\s+by"
    r")\b",
    re.I,
)

_PALL = re.compile(
    r"\b("
    r"better\s+with|better\s+when|relieved\s+by|relieved\s+with|"
    r"eases?\s+with|eases?\s+when|helped\s+by|"
    # Common volunteered phrasing the cue list previously missed
    # (e.g. "pain is improved by exercise", "exercise helps to improve my pain").
    r"helps?\s+(?:to\s+)?(?:improve|relieve|ease|reduce)|"
    r"helps?\s+with|help\s+with|"
    r"improved?\s+(?:by|with)|improves?\s+(?:by|with)|"
    r"better\s+at\s+night|better\s+in\s+the\s+morning|"
    r"better\s+when\s+(?:sitting|standing|walking|bending|lifting|twisting|running)|"
    r"better\s+with\s+(?:sitting|standing|walking|bending|lifting|twisting|movement|rest|ice|heat)|"
    r"after\s+rest|"
    r"goes\s+away\s+with|settles\s+with|subsides\s+with"
    r")\b",
    re.I,
)

def _dedupe_checklist_items_by_text(items: list[ChecklistItem]) -> list[ChecklistItem]:
    """Keep the first checklist row for each distinct ``text`` (case-insensitive)."""
    seen: set[str] = set()
    out: list[ChecklistItem] = []
    for it in items:
        key = it.text.casefold().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def _gliner_ner_items(text: str) -> list[ChecklistItem]:
    from app.services.gliner_ner import gliner_items_from_text

    raw: list[ChecklistItem] = []
    for row in gliner_items_from_text(text):
        raw.append(
            ChecklistItem(
                text=row["text"],
                kind="ner_entity",
                source="gliner",
                label=row["label"],
            )
        )
    return raw


def _span_ner_items(text: str) -> list[ChecklistItem]:
    """GliNER spans -> checklist rows (``source=gliner``), deduped by span text."""
    if not settings.ner_load or not text.strip():
        return []
    raw = _gliner_ner_items(text)
    return _dedupe_checklist_items_by_text(raw)


def _demographic_capture(groups: tuple[str | None, ...], label: str) -> str:
    """Pick the best capture group (sex patterns may include age + sex groups)."""
    parts = [g.strip() for g in groups if g and str(g).strip()]
    if not parts:
        return ""
    if label == "sex" and len(parts) > 1:
        return parts[-1]
    return parts[0]


def _pattern_demographics_age(text: str) -> list[ChecklistItem]:
    """Extract age when age-related trigger terms appear in the message."""
    if not _AGE_TRIGGERS.search(text):
        return []
    seen: set[str] = set()
    out: list[ChecklistItem] = []
    for pat in _AGE_VALUE_PATTERNS:
        for m in pat.finditer(text):
            snippet = _demographic_capture(m.groups(), "age") or m.group(0).strip()
            key = snippet.casefold()
            if not snippet or key in seen:
                continue
            seen.add(key)
            out.append(
                ChecklistItem(
                    text=snippet,
                    kind="demographic",
                    source="pattern",
                    label="age",
                )
            )
    return out


def _pattern_demographics_sex(text: str) -> list[ChecklistItem]:
    """Extract sex/gender when trigger terms or common self-report phrasing appear."""
    if not _SEX_TRIGGERS.search(text) and not _SEX_STANDALONE_HINT.search(text):
        return []
    seen: set[str] = set()
    out: list[ChecklistItem] = []
    for pat in _SEX_VALUE_PATTERNS:
        for m in pat.finditer(text):
            snippet = _demographic_capture(m.groups(), "sex") or m.group(0).strip()
            snippet = _canonical_sex_text(snippet)
            key = snippet.casefold()
            if not snippet or key in seen:
                continue
            seen.add(key)
            out.append(
                ChecklistItem(
                    text=snippet,
                    kind="demographic",
                    source="pattern",
                    label="sex",
                )
            )
    return out


def _pattern_durations(text: str) -> list[ChecklistItem]:
    out: list[ChecklistItem] = []
    for m in _DURATION.finditer(text):
        out.append(
            ChecklistItem(
                text=m.group(0).strip(),
                kind="duration",
                source="pattern",
                label="duration",
            )
        )
    return out


def _pattern_comorbidities(text: str) -> list[ChecklistItem]:
    return [
        ChecklistItem(text=m.group(0), kind="comorbidity", source="pattern", label="comorbidity")
        for m in _COMORBIDITY.finditer(text)
    ]


def _pain_severity_band(score: int) -> str | None:
    """Map a 0–10 pain score to mild (0–3), moderate (4–6), or severe (7–10)."""
    if 0 <= score <= 3:
        return "mild"
    if 4 <= score <= 6:
        return "moderate"
    if 7 <= score <= 10:
        return "severe"
    return None


_SEVERITY_CHECKLIST_LABEL = "symptom_severity"


def _pattern_pain_scale_severity(text: str) -> list[ChecklistItem]:
    """Extract 0–10 pain ratings (label ``symptom_severity``)."""
    seen_spans: set[str] = set()
    out: list[ChecklistItem] = []
    for m in _PAIN_SCALE_NUMERIC.finditer(text):
        span = m.group(0).strip()
        key = span.casefold()
        if key in seen_spans:
            continue
        try:
            score = int(m.group(1))
        except (TypeError, ValueError):
            continue
        band = _pain_severity_band(score)
        if band is None:
            continue
        seen_spans.add(key)
        out.append(
            ChecklistItem(
                text=span,
                kind="severity",
                source="pattern",
                label=_SEVERITY_CHECKLIST_LABEL,
            )
        )
    return out


def _pattern_descriptive_severity(text: str) -> list[ChecklistItem]:
    out: list[ChecklistItem] = []
    for m in _DESCRIPTIVE_SEVERITY.finditer(text):
        token = m.group(0).strip()
        out.append(
            ChecklistItem(
                text=token,
                kind="severity",
                source="pattern",
                label=_SEVERITY_CHECKLIST_LABEL,
            )
        )
    return out


def _pattern_severity(text: str) -> list[ChecklistItem]:
    """Pain severity: numeric 0–10 bands first, then descriptive terms."""
    scale_items = _pattern_pain_scale_severity(text)
    scale_spans = {it.text.casefold() for it in scale_items}
    out: list[ChecklistItem] = list(scale_items)
    for item in _pattern_descriptive_severity(text):
        if item.text.casefold() in scale_spans:
            continue
        out.append(item)
    return out


def _pattern_quality(text: str) -> list[ChecklistItem]:
    out: list[ChecklistItem] = []
    for m in _QUALITY.finditer(text):
        out.append(
            ChecklistItem(
                text=m.group(0).strip(),
                kind="symptom_quality",
                source="pattern",
                label="symptom_quality",
            )
        )
    return out


def _pattern_provoc(text: str) -> list[ChecklistItem]:
    out: list[ChecklistItem] = []
    for m in _PROVOC.finditer(text):
        out.append(
            ChecklistItem(
                text=m.group(0).strip(),
                kind="provocative",
                source="pattern",
                label="provocative",
            )
        )
    return out


def _pattern_pall(text: str) -> list[ChecklistItem]:
    out: list[ChecklistItem] = []
    for m in _PALL.finditer(text):
        out.append(
            ChecklistItem(
                text=m.group(0).strip(),
                kind="palliative",
                source="pattern",
                label="palliative",
            )
        )
    return out


def _safety_mentions(message_lower: str) -> list[ChecklistItem]:
    from app.services.policy import RISK_CATALOG

    found: list[ChecklistItem] = []
    for rid, terms in RISK_CATALOG.items():
        # sub-string matching on normalized message
        for term in terms:
            if term in message_lower:
                found.append(
                    ChecklistItem(
                        text=term,
                        kind="symptom",
                        source="safety_phrase",
                        label=rid,
                    )
                )
                break # exits inner loop, risk category is flagged and moves to next rid
    return found


def build_clinical_checklist(message: str) -> ClinicalChecklist:
    """Assemble pattern, safety, and optional NER layers into one checklist."""
    if not (message and message.strip()):
        return ClinicalChecklist()
    msg = message.strip()
    low = msg.lower() 
    items: list[ChecklistItem] = []

    items.extend(_pattern_demographics_age(msg))
    items.extend(_pattern_demographics_sex(msg))
    items.extend(_pattern_durations(msg))
    items.extend(_pattern_comorbidities(msg))
    items.extend(_pattern_severity(msg))
    items.extend(_pattern_quality(msg))
    items.extend(_pattern_provoc(msg))
    items.extend(_pattern_pall(msg))

    items.extend(_safety_mentions(low)) # red flags

    items.extend(_span_ner_items(msg))

    return ClinicalChecklist(items=items)

# convert ChecklistItems to EncoderEntities for storage
def _enc_entities_from_checklist(cl: ClinicalChecklist) -> list[EncoderEntity]:
    return [
        EncoderEntity(
            text=it.text,
            label=it.label if it.label else f"{it.kind}:{it.source}", # fallback synthesizing label from kind and source
        )
        for it in cl.items
    ]


def encode_user_message(message: str) -> EncoderOutput:
    """Checklist + entities + optional NER; full-message embedding for RAG when enabled."""
    from app.services.rag.embeddings import compute_query_embedding, rag_embedding_model_configured
    from app.services.rag.retrieval_query import dedupe_encoder_entities

    cl = build_clinical_checklist(message)
    entities = dedupe_encoder_entities(_enc_entities_from_checklist(cl))
    if not (message and message.strip()):
        return EncoderOutput(checklist=cl, entities=entities)
    if not settings.rag_load:
        return EncoderOutput(checklist=cl, entities=entities)
    if not rag_embedding_model_configured():
        return EncoderOutput(checklist=cl, entities=entities)
    pooled = compute_query_embedding(message.strip())
    if not pooled:
        _log.warning(
            "RAG query embedding empty (query=%r); check encoder at %s",
            message.strip()[:200],
            settings.encoder_model_dir,
        )
    return EncoderOutput(
        checklist=cl,
        entities=entities,
        pooled_embedding=pooled,
    )


def encoder_status_detail() -> str:
    from app.services.rag.embeddings import rag_embedding_model_configured

    parts: list[str] = []
    if rag_embedding_model_configured():
        parts.append("embedding ok")
    else:
        backend = getattr(settings, "rag_embedding_backend", "sentence_transformers")
        parts.append(
            f"RAG embedding model not configured (backend={backend!r}) "
            f"under {settings.encoder_model_dir}"
        )

    if settings.ner_load and settings.gliner_load:
        from app.services.gliner_ner import _get_gliner_model, gliner_configured, gliner_model_dir

        if gliner_configured() and _get_gliner_model() is not None:
            parts.append(f"GliNER ok ({gliner_model_dir()})")
        elif not gliner_configured():
            parts.append(f"GliNER not configured under {gliner_model_dir()}")
        else:
            parts.append(f"GliNER failed to load from {gliner_model_dir()}")
    elif settings.ner_load:
        parts.append("GliNER skipped (DIGIMSK_LOAD_GLINER=0)")
    else:
        parts.append("NER skipped (DIGIMSK_LOAD_NER=0)")

    return "; ".join(parts)


def encoder_is_available() -> bool:
    from app.services.rag.embeddings import rag_embedding_model_configured

    if not rag_embedding_model_configured():
        return False
    if settings.ner_load and settings.gliner_load:
        from app.services.gliner_ner import _get_gliner_model, gliner_configured

        return gliner_configured() and _get_gliner_model() is not None
    return True
