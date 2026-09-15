"""Aggregated dependency checks for ``GET /ready``."""

from __future__ import annotations

from app.config import settings
from app.orchestrator.checkpointing import get_checkpointer
from app.services.encoder import encoder_is_available, encoder_status_detail
from app.services.generator import generator_model_configured, generator_status_detail


def probe_rag() -> tuple[bool, str]:
    if not settings.rag_load:
        return True, "skipped (TRI_BACK_RAG=0)"
    try:
        from app.services.rag.store import get_sub_collection, list_sub_collections

        counts = []
        for name in list_sub_collections():
            counts.append(f"{name}={get_sub_collection(name).count()}")
        return True, "ok (" + ", ".join(counts) + ")"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def probe_checkpointer() -> tuple[bool, str]:
    try:
        saver = get_checkpointer()
        saver.conn.execute("BEGIN IMMEDIATE")
        saver.conn.commit()
        return True, "ok"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def probe_generator() -> tuple[bool, str]:
    if generator_model_configured():
        return True, generator_status_detail()
    return False, generator_status_detail()


def probe_encoder() -> tuple[bool, str]:
    detail = encoder_status_detail()
    if encoder_is_available():
        return True, detail
    return False, detail


def readiness_payload() -> dict:
    rag_ok, rag_detail = probe_rag()
    cp_ok, cp_detail = probe_checkpointer()
    gen_ok, gen_detail = probe_generator()
    enc_ok, enc_detail = probe_encoder()
    all_ok = rag_ok and cp_ok and gen_ok and enc_ok
    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": {
            "rag": {"ok": rag_ok, "detail": rag_detail},
            "checkpointer": {"ok": cp_ok, "detail": cp_detail},
            "generator": {"ok": gen_ok, "detail": gen_detail},
            "encoder": {"ok": enc_ok, "detail": enc_detail},
        },
    }
