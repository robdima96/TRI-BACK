"""Clinical NLP for one user turn: NER (optional), pattern extraction, checklist, entities.
RAG query embeddings are optional — disable with ``DIGIMSK_LOAD_RAG=0`` (see ``settings.rag_load``).
Pooled embeddings used for Chroma retrieval live in :mod:`app.services.rag.embeddings`;
``encode_user_message`` composes checklist/analysis with that vector when RAG is enabled.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings
from app.schemas import ChecklistItem, ClinicalChecklist, EncoderEntity, EncoderOutput

_log = logging.getLogger(__name__)

_ner_pipe: Any = None

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
    r"(?:\bfor\b\s*)?(\d{1,3})\s*(day|week|month|year)s?\b|"
    r"\b(chronic|acute|lifelong|since childhood)\b",
    re.I,
)

_SEVERITY = re.compile(
    r"\b("
    r"mild|moderate|mod\.?|severe|slight|slightly|minimal|"
    r"intense|excruciating|debilitating|marked|significant|"
    r"very\s+painful|quite\s+bad|unbearable|worst\s+\d|/10"
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
    r"better\s+with|better\s+when|relieved\s+by|eases?\s+with|helped\s+by|"
    r"better\s+at\s+night|better\s+in\s+the\s+morning|"
    r"better\s+when\s+(?:sitting|standing|walking|bending|lifting|twisting|running)|"
    r"better\s+with\s+(?:sitting|standing|walking|bending|lifting|twisting|movement|rest|ice|heat)|"
    r"improves?\s+with\s+rest|after\s+rest|"
    r"goes\s+away\s+with|settles\s+with|subsides\s+with"
    r")\b",
    re.I,
)

# get NER pipeline, return if loaded, else None and log warning
def _get_ner_pipeline() -> Any:
    global _ner_pipe
    if _ner_pipe is False:
        return None
    if _ner_pipe is not None:
        return _ner_pipe
    if not settings.ner_load:
        _ner_pipe = False
        return None
    try:
        from transformers import pipeline

        _ner_pipe = pipeline(
            "token-classification",
            model=settings.ner_model_id,
            aggregation_strategy="simple",
        )
        _log.info("NER pipeline loaded: %s", settings.ner_model_id)
    except Exception as e:
        _log.warning(
            "NER pipeline not available (%s); clinical extraction uses patterns only.", e
        )
        _ner_pipe = False
    return _ner_pipe if _ner_pipe is not False else None

# extract NER entities from text and convert to ChecklistItems
def _ner_items(text: str) -> list[ChecklistItem]:
    pipe = _get_ner_pipeline()
    if not pipe or not text.strip():
        return []
    out: list[ChecklistItem] = []
    try:
        for span in pipe(text, truncation=True, max_length=settings.encoder_max_length): # each span is a dict with word, entity_group, label etc.
            w = (span.get("word") or "").replace("##", "").strip()
            if not w or len(w) < 2:
                continue
            out.append(
                ChecklistItem(
                    text=w,
                    kind="ner_entity",
                    source="ner",
                    label=str(span.get("entity_group", span.get("label", ""))),
                )
            )
    except Exception as e:
        _log.debug("NER inference skipped: %s", e)
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


def _pattern_severity(text: str) -> list[ChecklistItem]:
    out: list[ChecklistItem] = []
    for m in _SEVERITY.finditer(text):
        out.append(
            ChecklistItem(
                text=m.group(0).strip(),
                kind="severity",
                source="pattern",
                label="severity",
            )
        )
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

    items.extend(_pattern_durations(msg))
    items.extend(_pattern_comorbidities(msg))
    items.extend(_pattern_severity(msg))
    items.extend(_pattern_quality(msg))
    items.extend(_pattern_provoc(msg))
    items.extend(_pattern_pall(msg))

    items.extend(_safety_mentions(low)) # red flags

    items.extend(_ner_items(msg)) # NER 

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
    """Checklist + entities + optional NER; pooled embedding for RAG when ``settings.rag_load``."""
    from app.services.rag.embeddings import compute_query_embedding, rag_embedding_model_configured

    cl = build_clinical_checklist(message)
    if not (message and message.strip()):
        return EncoderOutput(checklist=cl)  # if empty input, return empty checklist
    if not settings.rag_load:  # if RAG disabled in settings
        return EncoderOutput(checklist=cl).model_copy(
            update={"entities": _enc_entities_from_checklist(cl)}
        )  # copy with fields overridden
    if not rag_embedding_model_configured():  # if RAG embedding model not properly configured
        return EncoderOutput(checklist=cl)
    pooled = compute_query_embedding(message)
    if not pooled:
        _log.warning(
            "RAG query embedding empty for non-empty message; check encoder at %s (embeddings logs above)",
            settings.encoder_model_dir,
        )
    out = EncoderOutput(
        entities=[],
        pooled_embedding=pooled,
    )
    return out.model_copy( 
        update={
            "checklist": cl,
            "entities": _enc_entities_from_checklist(cl),
        }
    )


def encoder_is_available() -> bool:
    from app.services.rag.embeddings import rag_embedding_model_configured
    return rag_embedding_model_configured()
