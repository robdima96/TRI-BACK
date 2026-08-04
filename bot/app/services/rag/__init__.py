"""RAG: Chroma vector retrieval with query embeddings."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas import Evidence
from app.services.rag.chunk_retrieval import (
    chunk_matches_to_evidence,
    retrieve_chunk_matches,
)
from app.services.rag.embeddings import compute_query_embedding
from app.services.rag.store import (
    get_sub_collection,
    list_sub_collections,
    validate_sub_collection,
)

_log = logging.getLogger(__name__)


def retrieve_evidence(
    query: str,
    query_embedding: list[float] | None = None,
    top_k: int | None = None,
    *,
    sub_collections: list[str] | None = None,
) -> list[Evidence]:
    """Query Chroma with one embedding of the full user query (normalized text)."""
    if not settings.rag_load:
        return []
    k = top_k if top_k is not None else settings.rag_top_k
    targets = sub_collections or list_sub_collections()
    matches = retrieve_chunk_matches(
        query,
        query_embedding,
        top_k=k,
        sub_collections=targets,
    )
    return chunk_matches_to_evidence(matches)


def ingest_evidence_chunk(
    chunk_id: str,
    text: str,
    embedding: list[float] | None = None,
    *,
    sub_collection: str,
    source: str,
    metadatas: dict[str, Any] | None = None,
) -> None:
    """
    Upsert one chunk into the named evidence sub-collection.

    If ``embedding`` is omitted or its length mismatches ``encoder_embedding_dim``,
    the vector is computed with ``compute_query_embedding`` (same path as queries).
    """
    canonical = validate_sub_collection(sub_collection)
    vec: list[float]
    if embedding is not None and len(embedding) == settings.encoder_embedding_dim:
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
    coll = get_sub_collection(canonical)
    meta: dict[str, Any] = {
        "source": source,
        "chunk_id": chunk_id,
        "sub_collection": canonical,
    }
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
    _log.info(
        "ingested Chroma chunk %s into %r (source=%s)",
        chunk_id,
        canonical,
        source,
    )


def ingest_evidence_chunk_csv(
    *,
    sub_collection: str,
    csv_path: Path | str,
    registry_format: str = "auto",
) -> int:
    from app.services.rag.chunk_and_ingest import ingest_chunks_from_csv

    fmt = registry_format if registry_format in ("auto", "extracted", "manual") else "auto"
    return ingest_chunks_from_csv(
        sub_collection=sub_collection,
        chunks_csv=Path(csv_path),
        registry_format=fmt,  # type: ignore[arg-type]
    )
