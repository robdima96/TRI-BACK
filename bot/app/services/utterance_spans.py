"""Local SaT idea-span split + miniBERT question/statement labels.

Weights stay on disk (``TRI_BACK_SAT_SPLITTER_DIR``,
``TRI_BACK_QUERY_CLASSIFIER_DIR``). Runtime never hits the Hub.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.config import settings

_log = logging.getLogger(__name__)

SpanKind = Literal["polarity", "statement", "question"]

_WHOLE_POLARITY = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|yea|y|no|nope|nah|n|not\s+really|"
    r"i\s+don'?t\s+know|idk|unsure|not\s+sure|n/?a|no\s+idea|"
    r"not\s+certain|\?+)\s*[.!]*\s*$",
    re.I,
)
_LEADING_POLARITY = re.compile(
    r"^\s*(?:"
    r"i\s+don'?t\s+know|idk|unsure|not\s+sure|no\s+idea|not\s+certain|"
    r"yes|yeah|yep|yup|yea|"
    r"nope|nah|not\s+really|"
    r"no"
    r")\b\s*(?:[,.\-–—:]+|\s+but\b)\s*",
    re.I,
)
_PUNCT_SPLIT = re.compile(r"(?<=[.!?])\s+")

_QUESTION_LABELS = frozenset({"label_1", "question", "1"})
_STATEMENT_LABELS = frozenset({"label_0", "statement", "0"})

_sat_model: Any = None
_query_tokenizer: Any = None
_query_model: Any = None


@dataclass
class UtteranceAnalysis:
    polarity_spans: list[str] = field(default_factory=list)
    statement_spans: list[str] = field(default_factory=list)
    question_spans: list[str] = field(default_factory=list)
    raw_spans: list[str] = field(default_factory=list)

    @property
    def has_polarity(self) -> bool:
        return bool(self.polarity_spans)

    @property
    def has_statement(self) -> bool:
        return bool(self.statement_spans)

    @property
    def has_question(self) -> bool:
        return bool(self.question_spans)

    @property
    def polarity_only(self) -> bool:
        return self.has_polarity and not self.has_statement and not self.has_question

    @property
    def question_only(self) -> bool:
        return self.has_question and not self.has_statement and not self.has_polarity

    def to_dict(self) -> dict[str, Any]:
        return {
            "polarity_spans": list(self.polarity_spans),
            "statement_spans": list(self.statement_spans),
            "question_spans": list(self.question_spans),
            "raw_spans": list(self.raw_spans),
            "has_polarity": self.has_polarity,
            "has_statement": self.has_statement,
            "has_question": self.has_question,
        }


def analysis_from_dict(raw: dict[str, Any] | None) -> UtteranceAnalysis | None:
    if not isinstance(raw, dict):
        return None
    return UtteranceAnalysis(
        polarity_spans=[str(x) for x in (raw.get("polarity_spans") or []) if str(x).strip()],
        statement_spans=[
            str(x) for x in (raw.get("statement_spans") or []) if str(x).strip()
        ],
        question_spans=[str(x) for x in (raw.get("question_spans") or []) if str(x).strip()],
        raw_spans=[str(x) for x in (raw.get("raw_spans") or []) if str(x).strip()],
    )


def sat_splitter_configured() -> bool:
    d = Path(settings.sat_splitter_dir).resolve()
    return d.is_dir() and (d / "config.json").is_file()


def query_classifier_configured() -> bool:
    d = Path(settings.query_classifier_dir).resolve()
    return d.is_dir() and (d / "config.json").is_file()


def reset_utterance_models() -> None:
    """Test helper: drop cached SaT / miniBERT handles."""
    global _sat_model, _query_tokenizer, _query_model
    _sat_model = None
    _query_tokenizer = None
    _query_model = None


def _get_sat() -> Any:
    global _sat_model
    if _sat_model is False:
        return None
    if _sat_model is not None:
        return _sat_model
    if not settings.sat_splitter_load:
        _sat_model = False
        return None
    if not sat_splitter_configured():
        _log.warning("SaT splitter dir not found: %s", settings.sat_splitter_dir)
        _sat_model = False
        return None
    try:
        from wtpsplit import SaT

        model = SaT(str(Path(settings.sat_splitter_dir).resolve()))
        _sat_model = model
        _log.info("SaT splitter loaded from %s", settings.sat_splitter_dir)
        return _sat_model
    except Exception as exc:  # noqa: BLE001
        _log.warning("SaT splitter failed to load: %s", exc)
        _sat_model = False
        return None


def _get_query_classifier() -> tuple[Any, Any] | None:
    global _query_tokenizer, _query_model
    if _query_model is False:
        return None
    if _query_model is not None and _query_tokenizer is not None:
        return _query_tokenizer, _query_model
    if not settings.query_classifier_load:
        _query_model = False
        return None
    if not query_classifier_configured():
        _log.warning(
            "query classifier dir not found: %s", settings.query_classifier_dir
        )
        _query_model = False
        return None
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        path = str(Path(settings.query_classifier_dir).resolve())
        tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(
            path, local_files_only=True
        )
        model.eval()
        _query_tokenizer = tok
        _query_model = model
        _log.info("query classifier loaded from %s", path)
        return _query_tokenizer, _query_model
    except Exception as exc:  # noqa: BLE001
        _log.warning("query classifier failed to load: %s", exc)
        _query_model = False
        return None


def split_idea_spans(text: str) -> list[str]:
    """Split a user message into idea spans (punctuation optional)."""
    raw = (text or "").strip()
    if not raw:
        return []
    sat = _get_sat()
    if sat is not None:
        try:
            out = sat.split(raw)
            if isinstance(out, list) and out and isinstance(out[0], (list, tuple)):
                out = out[0]
            spans = [str(s).strip() for s in (out or []) if str(s).strip()]
            if spans:
                return spans
        except Exception as exc:  # noqa: BLE001
            _log.debug("SaT split failed; using fallback: %s", exc)
    if re.search(r"[.!?]", raw):
        parts = [p.strip() for p in _PUNCT_SPLIT.split(raw) if p.strip()]
        if parts:
            return parts
    return [raw]


def _label_to_kind(label: str) -> SpanKind:
    key = label.strip().casefold()
    if key in _QUESTION_LABELS:
        return "question"
    if key in _STATEMENT_LABELS:
        return "statement"
    if "question" in key:
        return "question"
    return "statement"


def classify_span_kind(text: str) -> SpanKind:
    """Label one idea span as question or statement (miniBERT, local files only)."""
    span = (text or "").strip()
    if not span:
        return "statement"
    loaded = _get_query_classifier()
    if loaded is None:
        return "question" if "?" in span else "statement"
    tok, model = loaded
    try:
        import torch

        inputs = tok(span, return_tensors="pt", truncation=True, max_length=128)
        with torch.no_grad():
            logits = model(**inputs).logits
        pred = int(logits.argmax(dim=-1).item())
        id2label = getattr(model.config, "id2label", None) or {}
        label = str(id2label.get(pred, id2label.get(str(pred), pred)))
        return _label_to_kind(label)
    except Exception as exc:  # noqa: BLE001
        _log.debug("query classifier inference failed: %s", exc)
        return "question" if "?" in span else "statement"


def _peel_leading_polarity(span: str) -> tuple[str | None, str]:
    text = (span or "").strip()
    if not text:
        return None, ""
    if _WHOLE_POLARITY.match(text):
        return text, ""
    match = _LEADING_POLARITY.match(text)
    if not match:
        return None, text
    peeled = match.group(0).strip().rstrip(",.:;-–—")
    remainder = text[match.end() :].strip()
    if not remainder:
        return text, ""
    return peeled or text[: match.end()].strip(), remainder


def classify_utterance(text: str) -> UtteranceAnalysis:
    """Split then label each idea span. Flags are additive."""
    raw = (text or "").strip()
    if not raw:
        return UtteranceAnalysis()
    if _WHOLE_POLARITY.match(raw):
        return UtteranceAnalysis(polarity_spans=[raw], raw_spans=[raw])

    spans = split_idea_spans(raw)
    analysis = UtteranceAnalysis(raw_spans=list(spans))
    for span in spans:
        polarity, remainder = _peel_leading_polarity(span)
        if polarity:
            analysis.polarity_spans.append(polarity)
        leftover = remainder.strip()
        if not leftover:
            continue
        kind = classify_span_kind(leftover)
        if kind == "question":
            analysis.question_spans.append(leftover)
        else:
            analysis.statement_spans.append(leftover)
    return analysis
