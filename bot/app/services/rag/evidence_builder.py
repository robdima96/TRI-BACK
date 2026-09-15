"""Build generator Evidence from RAG chunks and/or graph traversal."""

from __future__ import annotations

from app.config import settings
from app.schemas import ChunkMatch, Evidence
from app.services.graphrag.schemas import GraphTraversalTrace, TraversalStep
from app.services.rag.chunk_retrieval import chunk_matches_to_evidence


def _step_score(step: TraversalStep, default: float) -> float:
    if step.match_score is not None:
        return max(0.0, min(1.0, float(step.match_score)))
    return default


def _traversal_source(step: TraversalStep) -> str:
    factor = step.factor or "factor"
    condition = step.condition or "condition"
    rel = step.relationship or "RELATED_TO"
    if step.mediator and step.action == "traverse_mediated":
        return f"{factor} -[{rel}]-> {step.mediator} -> {condition}"
    return f"{factor} -[{rel}]-> {condition}"


def evidence_from_trace(trace: GraphTraversalTrace) -> list[Evidence]:
    """Map graph traversal steps and chunk nodes to Evidence for the generator."""
    items: list[Evidence] = []
    seen_paths: set[tuple[str, ...]] = set()
    seen_chunks: set[str] = set()

    for step in trace.steps:
        if step.action in ("traverse_direct", "traverse_mediated"):
            key = (
                step.action,
                step.factor or "",
                step.relationship or "",
                step.condition or "",
                step.mediator or "",
            )
            if key in seen_paths:
                continue
            seen_paths.add(key)
            snippet = (step.note or _traversal_source(step)).strip()
            items.append(
                Evidence(
                    source=_traversal_source(step),
                    snippet=snippet,
                    score=_step_score(step, 0.9),
                    chunk_id=step.chunk_id or None,
                )
            )
        elif step.action == "match_factor" and step.factor:
            items.append(
                Evidence(
                    source=f"factor:{step.factor}",
                    snippet=f"Checklist matched red-flag factor: {step.factor}",
                    score=_step_score(step, 0.85),
                )
            )
        elif step.action == "evidence_link" and step.chunk_id:
            cid = step.chunk_id
            if cid in seen_chunks:
                continue
            seen_chunks.add(cid)
            snippet = (step.note or cid).strip()
            items.append(
                Evidence(
                    source=cid,
                    snippet=snippet,
                    score=_step_score(step, 0.88),
                    chunk_id=cid,
                )
            )
        elif step.action == "match_chunk" and step.chunk_id:
            cid = step.chunk_id
            if cid in seen_chunks:
                continue
            seen_chunks.add(cid)
            snippet = (step.note or cid).strip()
            items.append(
                Evidence(
                    source=cid,
                    snippet=snippet,
                    score=_step_score(step, 0.82),
                    chunk_id=cid,
                )
            )

    for node in trace.nodes:
        if node.label != "Chunk":
            continue
        cid = str(node.properties.get("chunk_id") or node.name)
        if not cid or cid in seen_chunks:
            continue
        seen_chunks.add(cid)
        text = str(node.properties.get("chunk_string") or node.name).strip()
        items.append(
            Evidence(
                source=cid,
                snippet=text[:2000],
                score=0.86,
                chunk_id=cid,
            )
        )

    if trace.candidate_conditions:
        items.append(
            Evidence(
                source="graph:conditions",
                snippet="Candidate conditions: " + ", ".join(trace.candidate_conditions),
                score=0.8,
            )
        )

    return items


def _dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    seen: set[tuple[str, str, str | None]] = set()
    out: list[Evidence] = []
    for item in items:
        key = (item.source, item.snippet[:240], item.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_generator_evidence(
    *,
    trace: GraphTraversalTrace | None = None,
    chunk_matches: list[ChunkMatch] | None = None,
) -> list[Evidence]:
    """
    Merge evidence from enabled paths:

    - ``TRI_BACK_RAG=1``: Chroma + checklist lexical chunk hits
    - ``TRI_BACK_GRAPH_RAG=1``: graph traversal semantics and traversed chunks
    """
    items: list[Evidence] = []
    if settings.rag_load and chunk_matches:
        items.extend(chunk_matches_to_evidence(chunk_matches))
    if settings.graphrag_load and trace is not None:
        items.extend(evidence_from_trace(trace))
    return _dedupe_evidence(items)


def evidence_from_chunk_ids(
    chunk_ids: list[str],
    *,
    chunk_matches: list[ChunkMatch] | None = None,
    baseline: list[Evidence] | None = None,
) -> list[Evidence]:
    """Rebuild / extend Evidence using agent-touched chunk ids.

    Prefer snippets already present in ``chunk_matches`` or ``baseline``; fall
    back to the local graph CSV row text when GraphRAG is enabled.
    """
    wanted = [c for c in chunk_ids if c]
    if not wanted:
        return _dedupe_evidence(list(baseline or []))

    by_id: dict[str, Evidence] = {}
    for ev in baseline or []:
        if ev.chunk_id:
            by_id[ev.chunk_id] = ev

    match_by_id = {m.chunk_id: m for m in (chunk_matches or []) if m.chunk_id}
    missing: list[str] = []
    for cid in wanted:
        if cid in by_id:
            continue
        match = match_by_id.get(cid)
        if match is not None:
            by_id[cid] = Evidence(
                source=match.source,
                snippet=match.snippet,
                score=match.score,
                chunk_id=cid,
            )
        else:
            missing.append(cid)

    if missing and settings.graphrag_load:
        try:
            from app.services.graphrag import get_graph_client

            client = get_graph_client()
            for cid in missing:
                row = getattr(client, "_by_chunk_id", {}).get(cid)
                if row is None:
                    continue
                text = str(getattr(row, "chunk_string", "") or cid).strip()
                by_id[cid] = Evidence(
                    source=cid,
                    snippet=text[:2000],
                    score=0.86,
                    chunk_id=cid,
                )
        except Exception:  # noqa: BLE001 — keep baseline on lookup failure
            pass

    # Preserve baseline order, then append newly resolved agent chunk ids.
    ordered: list[Evidence] = list(baseline or [])
    seen = {(e.source, e.snippet[:240], e.chunk_id) for e in ordered}
    for cid in wanted:
        ev = by_id.get(cid)
        if ev is None:
            continue
        key = (ev.source, ev.snippet[:240], ev.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(ev)
    return ordered
