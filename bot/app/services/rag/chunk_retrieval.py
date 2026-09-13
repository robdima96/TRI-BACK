"""Semantic chunk retrieval from Chroma with graph-aligned chunk_id."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.config import settings
from app.schemas import ChecklistItem, ChecklistItemDump, ChunkMatch, Evidence
from app.services.rag.embeddings import compute_query_embedding
from app.services.rag.factor_patterns import known_chunk_ids
from app.services.rag.store import get_sub_collection, validate_sub_collection

_log = logging.getLogger(__name__)

_PRIMARY_COLLECTIONS = ("red_flags", "clinical_guidelines")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class _IndexedDoc:
    chunk_id: str
    source: str
    text: str
    sub_collection: str


# Compact lexical index: sub_collection -> docs. Built once at warmup (or
# lazily on first lexical match) so we never re-dump full Chroma collections.
_LEXICAL_DOC_INDEX: dict[str, tuple[_IndexedDoc, ...]] | None = None


def _distance_to_score(d: float) -> float:
    return max(0.0, min(1.0, 1.0 / (1.0 + max(0.0, d))))


def _embedding_dim_ok(query_embedding: list[float]) -> bool:
    return (
        len(query_embedding) == settings.encoder_embedding_dim if query_embedding else False
    )


def _parse_checklist(
    checklist: list[ChecklistItem] | list[ChecklistItemDump],
) -> list[ChecklistItem]:
    parsed: list[ChecklistItem] = []
    for row in checklist:
        if isinstance(row, ChecklistItem):
            parsed.append(row)
        else:
            parsed.append(ChecklistItem.model_validate(row))
    return parsed


def _checklist_search_patterns(items: list[ChecklistItem]) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    seen: set[str] = set()
    for item in items:
        text = _WS.sub(" ", (item.text or "").strip())
        if len(text) < 3:
            continue
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            patterns.append(re.compile(re.escape(text), re.IGNORECASE))
        for token in text.split():
            tok = token.casefold()
            if len(token) >= 4 and tok not in seen:
                seen.add(tok)
                patterns.append(re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE))
    return patterns


def _load_collection_docs(canonical: str) -> tuple[_IndexedDoc, ...]:
    coll = get_sub_collection(canonical)
    if coll.count() == 0:
        return ()
    res = coll.get(include=["documents", "metadatas"])
    ids0 = res.get("ids") or []
    docs0 = res.get("documents") or [""] * len(ids0)
    metas0 = res.get("metadatas") or [{}] * len(ids0)
    out: list[_IndexedDoc] = []
    for cid, doc, meta in zip(ids0, docs0, metas0):
        meta = meta or {}
        text = str(doc or "")
        if not text:
            continue
        out.append(
            _IndexedDoc(
                chunk_id=str(meta.get("chunk_id") or cid),
                source=str(meta.get("source", cid)),
                text=text,
                sub_collection=canonical,
            )
        )
    return tuple(out)


def warm_lexical_doc_index(
    *,
    sub_collections: list[str] | None = None,
    force: bool = False,
) -> int:
    """Load Chroma documents into an in-memory index for lexical matching.

    Returns the total number of indexed documents. Safe to call repeatedly;
    no-ops when the index is already warm unless ``force=True``.
    """
    global _LEXICAL_DOC_INDEX
    if not settings.rag_load:
        _LEXICAL_DOC_INDEX = {}
        return 0
    if _LEXICAL_DOC_INDEX is not None and not force:
        return sum(len(v) for v in _LEXICAL_DOC_INDEX.values())

    targets = sub_collections or list(_PRIMARY_COLLECTIONS)
    index: dict[str, tuple[_IndexedDoc, ...]] = {}
    for name in targets:
        try:
            canonical = validate_sub_collection(name)
        except ValueError:
            continue
        try:
            index[canonical] = _load_collection_docs(canonical)
        except Exception as exc:  # noqa: BLE001 — warmup must not raise
            _log.warning("lexical index load failed for %s: %s", canonical, exc)
            index[canonical] = ()
    _LEXICAL_DOC_INDEX = index
    total = sum(len(v) for v in index.values())
    _log.info(
        "lexical doc index ready (%d docs across %d collections)",
        total,
        len(index),
    )
    return total


def invalidate_lexical_doc_index() -> None:
    """Drop the cached index (e.g. after Chroma ingest/clear)."""
    global _LEXICAL_DOC_INDEX
    _LEXICAL_DOC_INDEX = None


def _indexed_docs_for(canonical: str) -> tuple[_IndexedDoc, ...]:
    global _LEXICAL_DOC_INDEX
    if _LEXICAL_DOC_INDEX is None:
        warm_lexical_doc_index()
    assert _LEXICAL_DOC_INDEX is not None
    cached = _LEXICAL_DOC_INDEX.get(canonical)
    if cached is not None:
        return cached
    docs = _load_collection_docs(canonical)
    _LEXICAL_DOC_INDEX[canonical] = docs
    return docs


def match_checklist_to_chroma_chunks(
    checklist: list[ChecklistItem] | list[ChecklistItemDump],
    *,
    sub_collections: list[str] | None = None,
) -> list[ChunkMatch]:
    """Lexical / regex match of checklist text against indexed Chroma documents."""
    if not settings.rag_load:
        return []
    items = _parse_checklist(checklist)
    patterns = _checklist_search_patterns(items)
    if not patterns:
        return []

    targets = sub_collections or list(_PRIMARY_COLLECTIONS)
    known = known_chunk_ids()
    by_id: dict[str, ChunkMatch] = {}

    for name in targets:
        try:
            canonical = validate_sub_collection(name)
        except ValueError:
            continue
        for doc in _indexed_docs_for(canonical):
            if known and doc.chunk_id not in known:
                _log.debug("chunk_id %r not in v1 inventory", doc.chunk_id)
            if not any(p.search(doc.text) for p in patterns):
                continue
            score = 0.78
            prev = by_id.get(doc.chunk_id)
            if prev is None or score > prev.score:
                by_id[doc.chunk_id] = ChunkMatch(
                    chunk_id=doc.chunk_id,
                    source=doc.source,
                    snippet=doc.text[:2000],
                    score=score,
                    sub_collection=canonical,
                )
    return sorted(by_id.values(), key=lambda c: c.score, reverse=True)


def _merge_chunk_matches(*groups: list[ChunkMatch]) -> list[ChunkMatch]:
    by_id: dict[str, ChunkMatch] = {}
    for group in groups:
        for match in group:
            prev = by_id.get(match.chunk_id)
            if prev is None or match.score > prev.score:
                by_id[match.chunk_id] = match
    return sorted(by_id.values(), key=lambda c: c.score, reverse=True)


def retrieve_chunk_matches(
    query: str,
    query_embedding: list[float] | None = None,
    *,
    top_k: int | None = None,
    sub_collections: list[str] | None = None,
) -> list[ChunkMatch]:
    """Query Chroma with Clinical_sBERT embedding; return chunk matches with ``chunk_id``."""
    if not settings.rag_load:
        return []

    k = top_k if top_k is not None else settings.rag_top_k
    text = (query or "").strip()
    if not text:
        return []

    vec = list(query_embedding or [])
    if not _embedding_dim_ok(vec):
        vec = compute_query_embedding(text)
    if not _embedding_dim_ok(vec):
        return []

    targets = sub_collections or list(_PRIMARY_COLLECTIONS)
    known = known_chunk_ids()
    candidates: list[ChunkMatch] = []

    for name in targets:
        try:
            canonical = validate_sub_collection(name)
        except ValueError:
            continue
        coll = get_sub_collection(canonical)
        count = coll.count()
        if count == 0:
            continue
        n_results = min(k, max(1, count))
        res = coll.query(
            query_embeddings=[vec],
            n_results=n_results,
            include=["distances", "documents", "metadatas"],
        )
        ids0 = res["ids"][0] if res["ids"] else []
        dists0 = res["distances"][0] if res.get("distances") else [0.0] * len(ids0)
        docs0 = res["documents"][0] if res.get("documents") else [""] * len(ids0)
        metas0 = res["metadatas"][0] if res.get("metadatas") else [{}] * len(ids0)

        for cid, d, doc, m in zip(ids0, dists0, docs0, metas0):
            meta = m or {}
            chunk_id = str(meta.get("chunk_id") or cid)
            if known and chunk_id not in known:
                _log.debug("chunk_id %r not in v1 inventory", chunk_id)
            src = str(meta.get("source", chunk_id))
            snippet = str(doc or "")[:2000]
            candidates.append(
                ChunkMatch(
                    chunk_id=chunk_id,
                    source=src,
                    snippet=snippet,
                    score=_distance_to_score(float(d)),
                    sub_collection=canonical,
                )
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:k]


def retrieve_rag_chunk_matches(
    query: str,
    query_embedding: list[float] | None,
    checklist: list[ChecklistItem] | list[ChecklistItemDump],
    *,
    top_k: int | None = None,
    sub_collections: list[str] | None = None,
) -> list[ChunkMatch]:
    """RAG path: Chroma semantic search + checklist lexical matches over chunk text."""
    semantic = retrieve_chunk_matches(
        query,
        query_embedding,
        top_k=top_k,
        sub_collections=sub_collections,
    )
    lexical = match_checklist_to_chroma_chunks(
        checklist,
        sub_collections=sub_collections,
    )
    k = top_k if top_k is not None else settings.rag_top_k
    return _merge_chunk_matches(semantic, lexical)[:k]


def chunk_matches_to_evidence(matches: list[ChunkMatch]) -> list[Evidence]:
    return [
        Evidence(
            source=m.source,
            snippet=m.snippet,
            score=m.score,
            chunk_id=m.chunk_id,
        )
        for m in matches
    ]
