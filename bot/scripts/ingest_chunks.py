"""CLI: upsert reviewed chunk registry CSV rows into a Chroma sub-collection.

Use after editing CSVs produced by ``scripts/extract_chunks.py`` or authored under
``<kb_dir>/chunks/manual/``.

Run from repo root::

    python scripts/ingest_chunks.py --sub-collection red_flags --registry extracted
    python scripts/ingest_chunks.py --sub-collection red_flags --registry manual
    python scripts/ingest_chunks.py --sub-collection red_flags --chunks-csv path/to.csv

Requires RAG embeddings (``DIGIMSK_ENCODER_DIR`` = Clinical_sBERT by default).
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
        default_kb_dir,
        ingest_chunks_from_csv,
        resolve_extracted_chunks_csv,
        resolve_manual_chunks_csv,
        resolve_kb_paths,
    )
    from app.services.rag.store import EVIDENCE_SUB_COLLECTIONS

    collections_help = ", ".join(EVIDENCE_SUB_COLLECTIONS)

    parser = argparse.ArgumentParser(
        description="Ingest reviewed chunk CSV into a Chroma sub-collection.",
    )
    parser.add_argument(
        "--sub-collection",
        required=True,
        help=f"Target Chroma sub-collection ({collections_help})",
    )
    parser.add_argument(
        "--kb-dir",
        type=Path,
        default=None,
        help="Knowledge-base root (used with --registry when --chunks-csv omitted)",
    )
    parser.add_argument(
        "--registry",
        choices=("auto", "extracted", "manual"),
        default="auto",
        help=(
            "Which default CSV under kb-dir: extracted (PDF pipeline), manual "
            "(curated), or auto-detect from headers (default: auto)"
        ),
    )
    parser.add_argument(
        "--chunks-csv",
        type=Path,
        default=None,
        help="Explicit path to chunk registry CSV",
    )
    parser.add_argument(
        "--chunks-registry-name",
        default=None,
        help="Filename under chunks/extracted/ or chunks/manual/ when using --kb-dir",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    if args.chunks_csv is not None:
        chunks_csv = args.chunks_csv.resolve()
    else:
        kb_dir = (args.kb_dir or default_kb_dir()).resolve()
        if args.registry == "manual":
            chunks_csv = resolve_manual_chunks_csv(
                kb_dir, chunks_registry_name=args.chunks_registry_name
            )
        elif args.registry == "extracted":
            chunks_csv = resolve_extracted_chunks_csv(
                kb_dir, chunks_registry_name=args.chunks_registry_name
            )
        else:
            _, _, chunks_csv = resolve_kb_paths(
                kb_dir,
                chunks_registry_name=args.chunks_registry_name,
                registry="extracted",
            )
            if not chunks_csv.is_file():
                chunks_csv = resolve_manual_chunks_csv(
                    kb_dir, chunks_registry_name=args.chunks_registry_name
                )

    return ingest_chunks_from_csv(
        sub_collection=args.sub_collection,
        chunks_csv=chunks_csv,
        registry_format=args.registry,
    )


if __name__ == "__main__":
    raise SystemExit(main())
