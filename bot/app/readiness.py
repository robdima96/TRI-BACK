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


def probe_graph() -> tuple[bool, str]:
    """Load the active triage pack (edges, factors, inventory) and its client."""
    if not settings.graphrag_load:
        return True, "skipped (TRI_BACK_GRAPH_RAG=0)"
    try:
        from app.triage_profiles import (
            get_triage_profile,
            graph_client_for_profile,
            load_ontology_for_profile,
        )

        profile = get_triage_profile()
        ontology = load_ontology_for_profile(profile)
        graph_client_for_profile(profile)
        return (
            True,
            f"ok ({profile.id}: {len(ontology.conditions)} conditions, "
            f"{len(ontology.all_factors)} factors)",
        )
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _public_detail(ok: bool, detail: str) -> str:
    """Omit exception text when the open-API flag is off."""
    if settings.allow_open_api:
        return detail
    return "ok" if ok else "error"


def readiness_payload() -> dict:
    rag_ok, rag_detail = probe_rag()
    cp_ok, cp_detail = probe_checkpointer()
    gen_ok, gen_detail = probe_generator()
    enc_ok, enc_detail = probe_encoder()
    graph_ok, graph_detail = probe_graph()
    all_ok = rag_ok and cp_ok and gen_ok and enc_ok and graph_ok
    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": {
            "rag": {"ok": rag_ok, "detail": _public_detail(rag_ok, rag_detail)},
            "checkpointer": {"ok": cp_ok, "detail": _public_detail(cp_ok, cp_detail)},
            "generator": {"ok": gen_ok, "detail": _public_detail(gen_ok, gen_detail)},
            "encoder": {"ok": enc_ok, "detail": _public_detail(enc_ok, enc_detail)},
            "graph": {"ok": graph_ok, "detail": _public_detail(graph_ok, graph_detail)},
        },
    }
