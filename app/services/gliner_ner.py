"""GliNER zero-shot span NER (optional; uses ``DIGIMSK_GLINER_MODEL_DIR``)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings

_log = logging.getLogger(__name__)

_gliner_model: Any = None

_DEFAULT_GLINER_LABELS: tuple[str, ...] = (
    "body part",
    "sign",
    "symptom",
    "symptom quality",
    "symptom severity",
    "symptom duration",
    "disease",
    "disorder",
    "symptom palliative factor",
    "symptom provocative factor",
    "injury",
    "trauma",
    "medication",
    "drug",
    "medical procedure",
    "risk factor",
)


def gliner_model_dir() -> Path:
    return Path(settings.gliner_model_dir).resolve()


def gliner_labels() -> list[str]:
    config_path = gliner_model_dir() / "gliner_config.json"
    if config_path.is_file():
        try:
            with config_path.open(encoding="utf-8") as f:
                data = json.load(f)
            for key in ("labels", "entity_types", "entity_labels"):
                raw = data.get(key)
                if isinstance(raw, list) and raw:
                    return [str(x).strip() for x in raw if str(x).strip()]
        except (OSError, json.JSONDecodeError) as e:
            _log.warning("could not read GliNER labels from %s: %s", config_path, e)
    return list(_DEFAULT_GLINER_LABELS)


def gliner_configured() -> bool:
    d = gliner_model_dir()
    return d.is_dir() and (d / "gliner_config.json").is_file()


def _get_gliner_model() -> Any:
    global _gliner_model
    if _gliner_model is False:
        return None
    if _gliner_model is not None:
        return _gliner_model
    if not settings.ner_load or not settings.gliner_load:
        _gliner_model = False
        return None
    if not gliner_configured():
        d = gliner_model_dir()
        cfg = d / "gliner_config.json"
        if not d.is_dir():
            _log.warning("GliNER model dir not found: %s", d)
        elif not cfg.is_file():
            _log.warning(
                "GliNER dir exists but gliner_config.json missing: %s", cfg
            )
        else:
            _log.warning("GliNER not configured under %s", d)
        _gliner_model = False
        return None
    try:
        from gliner import GLiNER

        _gliner_model = GLiNER.from_pretrained(
            str(gliner_model_dir()), local_files_only=True
        )
        _log.info("GliNER loaded from %s", gliner_model_dir())
    except Exception as e:
        _log.warning("GliNER not available (%s)", e)
        _gliner_model = False
    return _gliner_model if _gliner_model is not False else None


def gliner_items_from_text(text: str) -> list[dict[str, str]]:
    """GliNER spans as ``{text, label}`` dicts."""
    model = _get_gliner_model()
    if not model or not text.strip():
        return []
    labels = gliner_labels()
    raw: list[dict[str, str]] = []
    try:
        spans = model.predict_entities(
            text,
            labels,
            threshold=settings.gliner_ner_threshold,
        )
        for span in spans or []:
            w = (span.get("text") or span.get("word") or "").strip()
            if not w or len(w) < 2:
                continue
            raw.append(
                {
                    "text": w,
                    "label": str(span.get("label", span.get("entity_group", ""))),
                }
            )
    except Exception as e:
        _log.debug("GliNER inference skipped: %s", e)
        return []
    return raw
