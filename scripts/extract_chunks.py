"""CLI: auto-extract chunks from knowledge-base PDFs into a review CSV (no Chroma).

Writes ``<kb_dir>/chunks/extracted/<slug>_extracted.csv`` by default. Edit the CSV
on your machine, then load into Chroma with ``scripts/ingest_chunks.py``.

Run from repo root::

    python scripts/extract_chunks.py
    python scripts/extract_chunks.py --kb-dir "Knowledge Base/Red Flags"

Optional S2 layout chunking::

    pip install -e ".[chunk-ingest]"
    pip install git+https://github.com/Vprashant/s2-chunking-lib.git
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from app.services.rag.chunk_and_ingest import (
        MAX_CHUNK_TOKENS,
        _FALLBACK_MAX_CHARS,
        default_kb_dir,
        run_chunk_catalog,
    )

    parser = argparse.ArgumentParser(
        description=(
            "Extract chunks from PDFs under a knowledge-base folder and write "
            "chunks/extracted/<slug>_extracted.csv for review (no vector ingest)."
        ),
    )
    parser.add_argument(
        "--kb-dir",
        type=Path,
        default=default_kb_dir(),
        help="Knowledge-base root (docs/, sources/, chunks/extracted/)",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=None,
        help="Override <kb_dir>/docs",
    )
    parser.add_argument(
        "--sources-dir",
        type=Path,
        default=None,
        help="Override <kb_dir>/sources",
    )
    parser.add_argument(
        "--chunks-csv",
        type=Path,
        default=None,
        help="Override output CSV path",
    )
    parser.add_argument(
        "--chunks-registry-name",
        default=None,
        help="Filename under chunks/extracted/ when using --kb-dir",
    )
    parser.add_argument(
        "--chunk-id-prefix",
        default=None,
        help="Chunk id prefix (default: slug from kb folder name)",
    )
    parser.add_argument(
        "--corpus",
        default=None,
        help="corpus= metadata tag (default: slug from kb folder name)",
    )
    parser.add_argument(
        "--max-token-length",
        type=int,
        default=MAX_CHUNK_TOKENS,
        help=f"S2 max_token_length (default {MAX_CHUNK_TOKENS})",
    )
    parser.add_argument(
        "--no-s2-ocr",
        action="store_true",
        help="S2: use layout labels only (no EasyOCR); fallback likely for PDFs",
    )
    parser.add_argument(
        "--fallback-max-chars",
        type=int,
        default=_FALLBACK_MAX_CHARS,
        help="Max characters per chunk for pypdf fallback",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    return run_chunk_catalog(
        kb_dir=args.kb_dir.resolve(),
        docs_dir=args.docs_dir.resolve() if args.docs_dir else None,
        sources_dir=args.sources_dir.resolve() if args.sources_dir else None,
        chunks_csv=args.chunks_csv.resolve() if args.chunks_csv else None,
        chunks_registry_name=args.chunks_registry_name,
        max_token_length=args.max_token_length,
        s2_extract_text=not args.no_s2_ocr,
        fallback_max_chars=args.fallback_max_chars,
        chunk_id_prefix=args.chunk_id_prefix,
        corpus=args.corpus,
    )


if __name__ == "__main__":
    raise SystemExit(main())
