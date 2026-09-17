"""Eager load heavy dependencies so the first user turn is not a cold start.

Models (GliNER, optional Clinical_sBERT) and the Vertex ADC handshake are
otherwise lazy-loaded inside the first ``/api/v1/chat`` request, which can add
20–40s of one-time latency. Call :func:`warmup_runtime` from the FastAPI
lifespan so that cost is paid at process start instead.
"""

from __future__ import annotations

import logging
import time

from app.config import settings

_log = logging.getLogger(__name__)


def warmup_runtime() -> None:
    """Best-effort preload of encoder / GliNER / generator backends.

    Failures are logged and swallowed so a flaky warm-up never blocks API
    startup; the first real request can still try again.
    """
    t0 = time.perf_counter()
    _warmup_gliner()
    _warmup_sat_splitter()
    _warmup_query_classifier()
    _warmup_rag_embedding()
    _warmup_lexical_index()
    _warmup_generator()
    _log.info("runtime warmup finished in %.2fs", time.perf_counter() - t0)


def _warmup_gliner() -> None:
    if not (settings.ner_load and settings.gliner_load):
        _log.info("warmup: GliNER skipped (NER/GliNER disabled)")
        return
    try:
        from app.services.gliner_ner import _get_gliner_model, gliner_configured

        if not gliner_configured():
            _log.warning("warmup: GliNER not configured; skipping")
            return
        model = _get_gliner_model()
        if model is None:
            _log.warning("warmup: GliNER failed to load")
            return
        # Tiny inference pass so weights + runtime are fully primed.
        try:
            from app.services.gliner_ner import gliner_items_from_text

            gliner_items_from_text("warmup lower back pain")
        except Exception as exc:  # noqa: BLE001 — warm-up must not raise
            _log.debug("warmup: GliNER probe inference skipped: %s", exc)
        _log.info("warmup: GliNER ready")
    except Exception as exc:  # noqa: BLE001
        _log.warning("warmup: GliNER error: %s", exc)


def _warmup_sat_splitter() -> None:
    if not settings.sat_splitter_load:
        _log.info("warmup: SaT splitter skipped (TRI_BACK_LOAD_SAT_SPLITTER=0)")
        return
    try:
        from app.services.utterance_spans import (
            sat_splitter_configured,
            split_idea_spans,
        )

        if not sat_splitter_configured():
            _log.warning("warmup: SaT splitter not configured; skipping")
            return
        split_idea_spans("warmup yes I do have osteoarthritis but what about my back")
        _log.info("warmup: SaT splitter ready")
    except Exception as exc:  # noqa: BLE001
        _log.warning("warmup: SaT splitter error: %s", exc)


def _warmup_query_classifier() -> None:
    if not settings.query_classifier_load:
        _log.info("warmup: query classifier skipped (TRI_BACK_LOAD_QUERY_CLASSIFIER=0)")
        return
    try:
        from app.services.utterance_spans import (
            classify_span_kind,
            query_classifier_configured,
        )

        if not query_classifier_configured():
            _log.warning("warmup: query classifier not configured; skipping")
            return
        classify_span_kind("should I press on it?")
        classify_span_kind("if I stay still")
        _log.info("warmup: query classifier ready")
    except Exception as exc:  # noqa: BLE001
        _log.warning("warmup: query classifier error: %s", exc)


def _warmup_rag_embedding() -> None:
    if not settings.rag_load:
        _log.info("warmup: RAG embedding skipped (TRI_BACK_RAG=0)")
        return
    try:
        from app.services.rag.embeddings import (
            compute_query_embedding,
            rag_embedding_model_configured,
        )

        if not rag_embedding_model_configured():
            _log.warning("warmup: RAG embedding model not configured; skipping")
            return
        vec = compute_query_embedding("warmup")
        _log.info("warmup: RAG embedding ready (dim=%d)", len(vec))
    except Exception as exc:  # noqa: BLE001
        _log.warning("warmup: RAG embedding error: %s", exc)


def _warmup_lexical_index() -> None:
    if not settings.rag_load:
        _log.info("warmup: lexical Chroma index skipped (TRI_BACK_RAG=0)")
        return
    try:
        from app.services.rag.chunk_retrieval import warm_lexical_doc_index

        n = warm_lexical_doc_index()
        _log.info("warmup: lexical Chroma index ready (%d docs)", n)
    except Exception as exc:  # noqa: BLE001
        _log.warning("warmup: lexical Chroma index error: %s", exc)


def _warmup_generator() -> None:
    try:
        from app.services.generator import (
            generate_from_messages,
            generator_model_configured,
        )

        if not generator_model_configured():
            _log.warning("warmup: generator not configured; skipping")
            return
        # Tiny completion forces Vertex ADC + TLS + model handshake.
        generate_from_messages(
            [{"role": "user", "content": "Reply with exactly: ok"}],
            max_new_tokens=64,
            temperature=0.0,
        )
        _log.info("warmup: generator ready")
    except Exception as exc:  # noqa: BLE001
        _log.warning("warmup: generator error: %s", exc)
