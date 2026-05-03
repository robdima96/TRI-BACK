"""RAG: Chroma vector retrieval with query embeddings."""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.schemas import Evidence
from app.services.rag.embeddings import compute_query_embedding
from app.services.rag.store import get_evidence_collection

_log = logging.getLogger(__name__)

# convert cosine distance to similarity score [0,1]
def _distance_to_score(d: float) -> float:
    return max(0.0, min(1.0, 1.0 / (1.0 + max(0.0, d))))


def retrieve_evidence(
    query: str,
    query_embedding: list[float],
    top_k: int | None = None,
) -> list[Evidence]:

    if not settings.rag_load:
        return []
    k = top_k if top_k is not None else settings.rag_top_k
    coll = get_evidence_collection()

    dim_ok = (
        len(query_embedding) == settings.encoder_embedding_dim
        if query_embedding
        else False
    )
    if query_embedding and not dim_ok:
        _log.warning(
            "query embedding dim %s != encoder_embedding_dim %s; no Chroma query",
            len(query_embedding),
            settings.encoder_embedding_dim,
        )
    if dim_ok:
        n_results = min(k, max(1, coll.count()))
        if n_results == 0:
            return []
        res = coll.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["distances", "documents", "metadatas"],
        )
        out: list[Evidence] = []
        ids0 = res["ids"][0] if res["ids"] else []
        dists0 = res["distances"][0] if res.get("distances") else [0.0] * len(ids0)
        docs0 = res["documents"][0] if res.get("documents") else [""] * len(ids0)
        metas0 = res["metadatas"][0] if res.get("metadatas") else [{}] * len(ids0)
        for cid, d, doc, m in zip(ids0, dists0, docs0, metas0):
            src = (m or {}).get("source", cid)
            if doc is None:
                doc = ""
            out.append(
                Evidence(
                    source=str(src),
                    snippet=str(doc)[:2000],
                    score=_distance_to_score(float(d)),
                )
            )
        return out

    if not query_embedding:
        _log.debug("no query embedding; skipping Chroma query")
    return []

# Upsert one chunk into the evidence collection
def ingest_evidence_chunk(
    chunk_id: str,
    text: str,
    embedding: list[float] | None = None, # optional
    *,
    source: str,
    metadatas: dict[str, Any] | None = None,
) -> None:
    """
    If ``embedding`` is omitted or its length mismatches ``encoder_embedding_dim``,
    the vector is computed with ~app.services.rag.embeddings.compute_query_embedding
    (same path as queries: mean-pooled HF encoder in ``encoder_model_dir``).
    """
    vec: list[float]
    if (
        embedding is not None
        and len(embedding) == settings.encoder_embedding_dim
    ):
        vec = embedding
    else:
        if embedding is not None:
            _log.warning(
                "chunk %s embedding dim %s != encoder_embedding_dim %s; recomputing",
                chunk_id,
                len(embedding),
                settings.encoder_embedding_dim,
            )
        vec = compute_query_embedding(text)
        if len(vec) != settings.encoder_embedding_dim:
            raise ValueError(
                "could not produce encoder embedding "
                f"(got length {len(vec)}, expected "
                f"{settings.encoder_embedding_dim}); check encoder_model_dir "
                "and chunk text."
            )
    coll = get_evidence_collection()
    meta: dict[str, Any] = {"source": source, "chunk_id": chunk_id}
    if metadatas:
        for key, val in metadatas.items():
            if isinstance(val, (str, int, float, bool)):
                meta[key] = val
            else:
                meta[key] = str(val)
    coll.upsert(
        ids=[chunk_id],
        documents=[text],
        metadatas=[meta],
        embeddings=[vec],
    )
    _log.info("ingested Chroma chunk %s (source=%s)", chunk_id, source)
