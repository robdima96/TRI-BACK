"""Smoke-test production encoder + RAG on one user message.

Mirrors ``encode_input_node`` + ``retrieve_evidence_node`` (same models and settings
as the chatbot): normalize → checklist (regex, safety phrases, GliNER) → risk hits →
full-message Clinical_sBERT embedding → Chroma top-k.

Run from the repo root::

    python scripts/encode_rag_smoke.py
    python scripts/encode_rag_smoke.py --query "27 year old female, low back pain after a fall"
    python scripts/encode_rag_smoke.py --output tests/data/results/my_run.txt

Writes ``tests/data/results/encode_rag_smoke_results.txt`` by default (and prints the
same report to stdout).

Exit codes: 0 ok, 1 config/embedding failure, 2 no retrieval rows.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUT = _ROOT / "tests" / "data" / "results" / "encode_rag_smoke_results.txt"
_SOURCE_ORDER = ("pattern", "safety_phrase", "gliner")

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in (
        "chromadb",
        "httpx",
        "httpcore",
        "huggingface_hub",
        "urllib3",
        "transformers",
        "filelock",
        "gliner",
        "sentence_transformers",
        "tqdm",
    ):
        logging.getLogger(name).setLevel(logging.ERROR if not verbose else logging.WARNING)


def _format_config_block(
    *,
    gliner_ok: bool,
    gliner_configured: bool,
    no_ner: bool,
) -> list[str]:
    from app.config import settings as s

    lines = [
        "=== Configuration (production settings) ===",
        f"  rag_load:                 {s.rag_load}",
        f"  ner_load:                 {s.ner_load}",
        f"  gliner_load:              {s.gliner_load}",
        f"  encoder_model_dir (RAG):  {s.encoder_model_dir}",
        f"  rag_embedding_backend:    {s.rag_embedding_backend}",
        f"  encoder_embedding_dim:    {s.encoder_embedding_dim}",
        f"  gliner_model_dir (NER):   {s.gliner_model_dir}",
        f"  gliner configured:        {gliner_configured}",
        f"  gliner loaded this run:   {gliner_ok}",
        f"  chroma_persist_path:      {s.chroma_persist_path}",
        f"  rag_top_k:                {s.rag_top_k}",
    ]
    if no_ner:
        lines.append("  note: --no-ner set (GliNER spans disabled for this run)")
    return lines


def _format_checklist_by_source(items: list[dict[str, str]]) -> list[str]:
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in items:
        by_source[row.get("source", "?")].append(row)

    layer_titles = {
        "pattern": "Regex / pattern extraction",
        "safety_phrase": "Safety phrase extraction (RISK_CATALOG substrings)",
        "gliner": "GliNER-BioMed span NER",
    }
    lines: list[str] = ["=== Clinical checklist by extractor ==="]
    keys = [k for k in _SOURCE_ORDER if k in by_source] + sorted(
        k for k in by_source if k not in _SOURCE_ORDER
    )
    if not keys:
        lines.append("  (no checklist items)")
        return lines

    for source in keys:
        rows = by_source[source]
        title = layer_titles.get(source, source)
        lines.append("")
        lines.append(f"--- {title} [{source}] ({len(rows)} item(s)) ---")
        for i, row in enumerate(rows, 1):
            lines.append(
                f"  {i}. text={row.get('text', '')!r}  "
                f"kind={row.get('kind', '')!r}  label={row.get('label', '')!r}"
            )
    counts = Counter(r.get("source", "?") for r in items)
    lines.extend(
        [
            "",
            "Checklist counts:",
            f"  pattern (regex):     {counts.get('pattern', 0)}",
            f"  gliner (spans):      {counts.get('gliner', 0)}",
            f"  safety_phrase:       {counts.get('safety_phrase', 0)}",
            f"  total:               {sum(counts.values())}",
        ]
    )
    return lines


def _format_risk_hits(risk_hits: list[str]) -> list[str]:
    lines = ["=== Risk hits (hits_for_clinical_path) ==="]
    if not risk_hits:
        lines.append("  (none)")
    else:
        for rid in risk_hits:
            lines.append(f"  - {rid}")
    return lines


def _format_rag_section(
    *,
    normalized_query: str,
    embedding_dim: int,
    top_k: int,
    collection_counts: list[tuple[str, int]],
    hits: list[tuple[int, float, str, str, str]],
) -> list[str]:
    lines = [
        "=== RAG retrieval (full normalized message; production path) ===",
        f"  embedded_query: {normalized_query!r}",
        f"  query_embedding_dim: {embedding_dim}",
        f"  top_k: {top_k}",
        "  Chroma sub-collections:",
    ]
    for name, count in collection_counts:
        lines.append(f"    {name!r}: {count} document(s)")
    if not hits:
        lines.append("")
        lines.append("  (no retrieval hits)")
        return lines

    lines.append("")
    lines.append("  Rank | Score   | Source")
    lines.append("  " + "-" * 72)
    for rank, score, brief_source, chunk_id, snippet in hits:
        lines.append(f"  {rank:4d} | {score:.4f} | {brief_source}")
        lines.append(f"         chunk_id: {chunk_id}")
        preview = snippet.replace("\n", " ").strip()
        if len(preview) > 500:
            preview = preview[:500] + "..."
        lines.append(f"         {preview}")
        lines.append("")
    return lines


def build_report(
    *,
    user_query: str,
    normalized_query: str,
    checklist_rows: list[dict[str, str]],
    entity_rows: list[dict[str, str]],
    risk_hits: list[str],
    top_k: int,
    embedding_dim: int,
    collection_counts: list[tuple[str, int]],
    hits: list[tuple[int, float, str, str, str]],
    config_lines: list[str],
) -> str:
    header = [
        "encode_rag_smoke — production encoder + RAG",
        f"generated_utc: {datetime.now(timezone.utc).isoformat()}",
        "",
        "=== User message ===",
        f"  raw:        {user_query!r}",
        f"  normalized: {normalized_query!r}",
        "",
    ]
    entities_block = [
        f"=== Deduped encoder entities ({len(entity_rows)}; not used for Chroma) ===",
    ]
    if not entity_rows:
        entities_block.append("  (none)")
    else:
        for i, row in enumerate(entity_rows, 1):
            entities_block.append(
                f"  {i}. text={row.get('text', '')!r}  label={row.get('label', '')!r}"
            )
    entities_block.append("")

    parts = [
        *header,
        *config_lines,
        "",
        *_format_checklist_by_source(checklist_rows),
        "",
        *_format_risk_hits(risk_hits),
        "",
        *entities_block,
        *_format_rag_section(
            normalized_query=normalized_query,
            embedding_dim=embedding_dim,
            top_k=top_k,
            collection_counts=collection_counts,
            hits=hits,
        ),
    ]
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Production-path smoke: regex + safety + GliNER checklist, risk hits, "
            "full-query RAG."
        ),
    )
    parser.add_argument(
        "--query",
        default="superficial heat for acute low back pain",
        help="User message (normalized like the API)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Report path (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--no-ner",
        action="store_true",
        help="Disable GliNER (DIGIMSK_LOAD_NER=0); not production-default",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logs",
    )
    args = parser.parse_args()
    _configure_logging(verbose=args.verbose)

    os.environ.setdefault("DIGIMSK_LOAD_RAG", "1")
    if args.no_ner:
        os.environ["DIGIMSK_LOAD_NER"] = "0"
        os.environ["DIGIMSK_LOAD_GLINER"] = "0"
    else:
        os.environ.setdefault("DIGIMSK_LOAD_NER", "1")
        os.environ.setdefault("DIGIMSK_LOAD_GLINER", "1")

    from app.config import settings
    from app.services.encoder import encode_user_message
    from app.services.gliner_ner import _get_gliner_model, gliner_configured
    from app.services.policy import hits_for_clinical_path
    from app.services.preprocess import normalize_user_text
    from app.services.rag import retrieve_evidence
    from app.services.rag.chunk_and_ingest import brief_source_citation
    from app.services.rag.embeddings import rag_embedding_model_configured
    from app.services.rag.store import get_sub_collection, list_sub_collections

    if not settings.rag_load:
        sys.stderr.write("RAG is disabled (set DIGIMSK_LOAD_RAG=1).\n")
        return 1
    if not rag_embedding_model_configured():
        sys.stderr.write(
            f"RAG encoder not configured — check DIGIMSK_ENCODER_DIR: "
            f"{settings.encoder_model_dir}\n"
        )
        return 1

    user_query = args.query.strip()
    if not user_query:
        sys.stderr.write("Provide a non-empty --query.\n")
        return 1

    gliner_ok = False
    if settings.ner_load and settings.gliner_load and not args.no_ner:
        gliner_ok = gliner_configured() and _get_gliner_model() is not None

    normalized = normalize_user_text(user_query)
    enc = encode_user_message(normalized)

    checklist_rows = [it.model_dump() for it in enc.checklist.items]
    risk_hits = hits_for_clinical_path(enc.checklist, normalized)

    if len(enc.pooled_embedding) != settings.encoder_embedding_dim:
        sys.stderr.write(
            f"Query embedding length {len(enc.pooled_embedding)} "
            f"(expected {settings.encoder_embedding_dim}).\n"
        )
        return 1

    collection_counts: list[tuple[str, int]] = []
    for name in list_sub_collections():
        collection_counts.append((name, get_sub_collection(name).count()))

    k = settings.rag_top_k
    evidence = retrieve_evidence(normalized, enc.pooled_embedding, top_k=k)
    hits: list[tuple[int, float, str, str, str]] = []
    for rank, ev in enumerate(evidence, 1):
        hits.append(
            (
                rank,
                ev.score,
                brief_source_citation(ev.source),
                ev.source,
                ev.snippet,
            )
        )

    config_lines = _format_config_block(
        gliner_ok=gliner_ok,
        gliner_configured=gliner_configured(),
        no_ner=args.no_ner,
    )
    report = build_report(
        user_query=user_query,
        normalized_query=normalized,
        checklist_rows=checklist_rows,
        entity_rows=[e.model_dump() for e in enc.entities],
        risk_hits=risk_hits,
        top_k=k,
        embedding_dim=len(enc.pooled_embedding),
        collection_counts=collection_counts,
        hits=hits,
        config_lines=config_lines,
    )

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    sys.stdout.write(report)
    sys.stdout.flush()
    print(f"\nWrote report to {output_path}", file=sys.stderr)

    if not hits:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
