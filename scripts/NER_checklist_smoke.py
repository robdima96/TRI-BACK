"""Smoke-test clinical checklist + encoder entities on one user message.

Runs the same encoder path as the chatbot (normalize → ``build_clinical_checklist``
/ ``encode_user_message``), with NER enabled by default for this script.

Run from the repo root::

    python scripts/NER_checklist_smoke.py -m "I fell yesterday and have severe low back pain."
    python scripts/NER_checklist_smoke.py --no-ner -m "diabetes for 5 years, pain 8/10"

Uses ``DIGIMSK_LOAD_NER`` + ``DIGIMSK_GLINER_MODEL_DIR`` (GliNER-BioMed). RAG embeddings
use ``DIGIMSK_ENCODER_DIR`` (Clinical_sBERT) separately.
Use ``--no-rag`` (default) to skip RAG / DeBERTa load.

Exit codes: 0 ok, 1 empty message, 2 NER enabled but GliNER did not load.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Apply toggles before ``app.config`` is imported (first app import below).
os.environ.setdefault("DIGIMSK_LOAD_NER", "1")
os.environ.setdefault("DIGIMSK_LOAD_RAG", "0")

_SOURCE_ORDER = ("pattern", "safety_phrase", "gliner")


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s %(message)s",
        force=True,
    )
    for name in (
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


def _count_by_source(items: list[dict[str, str]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in items:
        counts[row.get("source", "?")] += 1
    return dict(counts)


def _format_summary(counts: dict[str, int]) -> str:
    pattern_n = counts.get("pattern", 0)
    gliner_n = counts.get("gliner", 0)
    safety_n = counts.get("safety_phrase", 0)
    known = pattern_n + gliner_n + safety_n
    total = sum(counts.values())
    lines = [
        f"  Total checklist items: {total}",
        f"  pattern (regex + demographics): {pattern_n}",
        f"  gliner (GliNER-BioMed spans): {gliner_n}",
        f"  safety_phrase: {safety_n}",
    ]
    if total != known:
        lines.append(f"  other sources: {total - known}")
    lines.append(
        "  Note: pattern, safety_phrase, and gliner are separate extractors."
    )
    return "\n".join(lines)


def _format_checklist_sections(items: list[dict[str, str]]) -> str:
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in items:
        by_source[row.get("source", "?")].append(row)

    keys = [k for k in _SOURCE_ORDER if k in by_source] + sorted(
        k for k in by_source if k not in _SOURCE_ORDER
    )
    lines: list[str] = []
    for source in keys:
        rows = by_source[source]
        kind_counts = Counter(r.get("kind", "") for r in rows)
        kind_part = ", ".join(f"{k}={v}" for k, v in sorted(kind_counts.items()) if k)
        header = f"  [{source}] ({len(rows)} item(s))"
        if kind_part:
            header += f" — kinds: {kind_part}"
        lines.append(header)
        for i, row in enumerate(rows, 1):
            lines.append(
                f"    {i}. text={row.get('text', '')!r}  "
                f"kind={row.get('kind', '')!r}  label={row.get('label', '')!r}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_deduped_entities(entities: list[dict[str, str]], *, retrieval_query: str) -> str:
    if not entities:
        return "  (none — RAG retrieval would be skipped)"
    lines = [
        f"  Deduped count: {len(entities)} (used for Chroma matching, not full message)",
        f"  Combined retrieval_query: {retrieval_query!r}",
        "",
    ]
    for i, row in enumerate(entities, 1):
        lines.append(
            f"  {i}. text={row.get('text', '')!r}  label={row.get('label', '')!r}"
        )
    return "\n".join(lines)


def _build_report(
    *,
    text: str,
    normalized: str,
    checklist: list[dict[str, str]],
    entities: list[dict[str, str]],
    retrieval_query: str,
    config_lines: list[str],
) -> str:
    counts = _count_by_source(checklist)
    total = len(checklist)
    sections = [
        "=== Configuration ===",
        *config_lines,
        "",
        "=== Raw message ===",
        text,
        "",
        "=== Normalized message (chat pipeline input) ===",
        normalized or "(empty)",
        "",
        "=== Extraction summary ===",
        _format_summary(counts),
        "",
        f"=== Clinical checklist ({total} item(s)) ===",
        _format_checklist_sections(checklist),
        "",
        f"=== Encoder entities ({len(entities)} deduped; RAG query source) ===",
        _format_deduped_entities(entities, retrieval_query=retrieval_query),
    ]
    return "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run encoder checklist + entity extraction on one message.",
    )
    parser.add_argument(
        "message",
        nargs="?",
        default="",
        help="User message (positional)",
    )
    parser.add_argument(
        "-m",
        "--message",
        dest="message_opt",
        default="",
        help="User message (alternative to positional)",
    )
    parser.add_argument(
        "--no-ner",
        action="store_true",
        help="Disable span NER (GliNER) for this run",
    )
    parser.add_argument(
        "--rag",
        action="store_true",
        help="Also compute RAG query embedding (loads encoder backbone)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG logging",
    )
    args = parser.parse_args(argv)
    _configure_logging(verbose=args.verbose)

    if args.no_ner:
        os.environ["DIGIMSK_LOAD_NER"] = "0"
    if args.rag:
        os.environ["DIGIMSK_LOAD_RAG"] = "1"

    from app.config import settings
    from app.services.encoder import encode_user_message
    from app.services.gliner_ner import _get_gliner_model, gliner_configured, gliner_model_dir
    from app.services.preprocess import normalize_user_text
    text = (args.message_opt or args.message or "").strip()
    if not text:
        sys.stderr.write("Provide a message via positional arg or -m/--message.\n")
        return 1

    normalized = normalize_user_text(text)
    enc = encode_user_message(normalized)
    checklist = [it.model_dump() for it in enc.checklist.items]
    entities = [e.model_dump() for e in enc.entities]
    retrieval_query = normalized if settings.rag_load else ""

    gliner_ok = gliner_configured()
    if settings.ner_load and settings.gliner_load:
        gliner_ok = _get_gliner_model() is not None
    if settings.ner_load and settings.gliner_load and not gliner_ok:
        sys.stderr.write(
            "NER is enabled but GliNER failed to load; "
            "check DIGIMSK_GLINER_MODEL_DIR and docs/NER_PIPELINE.md.\n"
        )
        return 2

    config_lines = [
        f"  ner_load:              {settings.ner_load}",
        f"  gliner_load:           {settings.gliner_load}",
        f"  gliner_model_dir:      {settings.gliner_model_dir}",
        f"  GliNER (resolved):     {gliner_model_dir()}",
        f"  gliner configured:     {gliner_configured()}",
        f"  GliNER loaded:         {gliner_ok}",
        f"  gliner_ner_threshold:  {settings.gliner_ner_threshold}",
        f"  encoder_model_dir (RAG): {settings.encoder_model_dir}",
        f"  rag_load:              {settings.rag_load}",
        f"  query embedding dim:   {len(enc.pooled_embedding) or '(none)'}",
        f"  rag_query (full text): {repr(retrieval_query) if retrieval_query else '(none)'}",
    ]

    report = _build_report(
        text=text,
        normalized=normalized,
        checklist=checklist,
        entities=entities,
        retrieval_query=retrieval_query,
        config_lines=config_lines,
    )
    sys.stdout.write(report + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
