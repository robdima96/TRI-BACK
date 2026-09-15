"""Fill ``retrieval`` column from the vignette query column (full-message RAG).

Embeds the full vignette text (normalized) and queries Chroma via production
``retrieve_evidence`` — same path as the chatbot.

Usage::

    python scripts/fill_vignette_retrieval_column.py
    python scripts/fill_vignette_retrieval_column.py --first-row 2 --last-row 10
    python scripts/fill_vignette_retrieval_column.py --query-col vignette
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_XLSX = (
    _ROOT / "tests" / "data" / "results" / "NER_checklist_matching_with_vignettes.xlsx"
)

os.environ.setdefault("DIGIMSK_LOAD_RAG", "1")


def _format_retrieval_for_xlsx(
    *,
    retrieval_query: str,
    top_k: int,
    hits: list[tuple[str, str, float, str]],
) -> str:
    """Top-k Chroma hits with scores (``rag_smoke.py``-style blocks)."""
    lines: list[str] = [
        f"retrieval_query: {retrieval_query!r}",
        f"top_k: {top_k}",
    ]
    if not hits:
        lines.append("")
        lines.append("(no retrieval hits)")
        return "\n".join(lines)

    for i, (chunk_id, sub_collection, score, text) in enumerate(hits, 1):
        lines.append("")
        lines.append(
            f"--- {i}. chunk_id={chunk_id} "
            f"sub_collection={sub_collection} score={score:.4f} ---"
        )
        lines.append(text)
    return "\n".join(lines)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in ("chromadb", "httpx", "transformers", "gliner", "tqdm"):
        logging.getLogger(name).setLevel(logging.ERROR)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill vignette xlsx retrieval column from full vignette query text.",
    )
    parser.add_argument("--xlsx", type=Path, default=_DEFAULT_XLSX)
    parser.add_argument("--first-row", type=int, default=2)
    parser.add_argument("--last-row", type=int, default=10)
    parser.add_argument(
        "--query-col",
        default="vignette",
        help="Column with full patient vignette / query text (fallback: column B)",
    )
    parser.add_argument("--retrieval-col", default="retrieval")
    args = parser.parse_args()
    _configure_logging()

    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.stderr.write("openpyxl required: pip install openpyxl\n")
        return 1

    from app.config import settings
    from app.services.encoder import encode_user_message
    from app.services.preprocess import normalize_user_text
    from app.services.rag import retrieve_evidence
    from app.services.rag.embeddings import rag_embedding_model_configured

    if not settings.rag_load:
        sys.stderr.write("RAG is disabled (set TRI_BACK_LOAD_RAG=1).\n")
        return 1
    if not rag_embedding_model_configured():
        sys.stderr.write(
            f"Encoder layout invalid — check DIGIMSK_ENCODER_DIR: "
            f"{settings.encoder_model_dir}\n"
        )
        return 1

    wb = load_workbook(args.xlsx)
    ws = wb.active
    headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
    q_col = headers.get(args.query_col) or 2
    r_col = headers.get(args.retrieval_col)
    if not r_col:
        sys.stderr.write(
            f"Missing column {args.retrieval_col!r}; found {list(headers)}\n"
        )
        return 1

    k = settings.rag_top_k

    for row in range(args.first_row, args.last_row + 1):
        raw = ws.cell(row, q_col).value
        if raw is None or not str(raw).strip():
            sys.stderr.write(f"Row {row}: empty query column, skipping.\n")
            continue
        normalized = normalize_user_text(str(raw).strip())
        enc = encode_user_message(normalized)
        if len(enc.pooled_embedding) != settings.encoder_embedding_dim:
            sys.stderr.write(
                f"Row {row}: embedding length {len(enc.pooled_embedding)} "
                f"(expected {settings.encoder_embedding_dim}).\n"
            )
            continue
        evidence = retrieve_evidence(
            normalized,
            enc.pooled_embedding,
            top_k=k,
        )
        hits = [
            (ev.source, ev.source, ev.score, ev.snippet) for ev in evidence
        ]
        ws.cell(row, r_col).value = _format_retrieval_for_xlsx(
            retrieval_query=normalized,
            top_k=k,
            hits=hits,
        )
        source = ws.cell(row, headers.get("source", 1)).value
        print(f"row {row} {source}: full-query -> {len(hits)} hit(s)")

    wb.save(args.xlsx)
    print(f"Saved {args.xlsx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
