"""Run one user message through the full chatbot pipeline with a detailed trace.

Exercises the same nodes as production (preprocess → encode → coverage → planner →
retrieve → generate → policy) but **bypasses intake questions**: ``question_mode`` is
forced off so the graph always continues to ``retrieve_evidence`` even when coverage
is incomplete. Coverage and planner output are still computed and printed.

Batch mode reads queries from column **B** (rows 2–11) of the vignette results sheet
and writes the trace to column **F** (F2–F11).

Usage::

    python scripts/full_test_.py -m "I have low back pain for 3 weeks"
    python scripts/full_test_.py --batch
    python scripts/full_test_.py --batch --csv path/to/file.csv --first-row 2 --last-row 11
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from langchain_core.messages import HumanMessage

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_DEFAULT_CSV = (
    _ROOT / "tests" / "data" / "results" / "NER_checklist_matching_with_vignettes.csv"
)
_SOURCE_ORDER = ("pattern", "safety_phrase", "gliner")
_RESULT_COL = 5  # column F (0-based)
_QUERY_COL = 1  # column B


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


def _format_checklist_layer(
    title: str,
    items: list[dict[str, str]],
) -> list[str]:
    """Format one extractor layer (pattern / safety_phrase / gliner)."""
    lines = [f"=== {title} ({len(items)} item(s)) ==="]
    if not items:
        lines.append("  (none)")
        return lines
    for i, row in enumerate(items, 1):
        lines.append(
            f"  {i}. text={row.get('text', '')!r}  "
            f"kind={row.get('kind', '')!r}  label={row.get('label', '')!r}"
        )
    return lines


def _format_checklist_by_source(checklist: list[dict[str, str]]) -> list[str]:
    """Group merged checklist rows by ``source`` (regex, safety, GliNER)."""
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in checklist:
        by_source[row.get("source", "?")].append(row)

    lines: list[str] = ["=== Encoder checklist by extractor ==="]
    layer_titles = {
        "pattern": "Pattern / regex + demographics",
        "safety_phrase": "Safety substring (RISK_CATALOG)",
        "gliner": "GliNER-BioMed spans",
    }
    keys = [k for k in _SOURCE_ORDER if k in by_source] + sorted(
        k for k in by_source if k not in _SOURCE_ORDER
    )
    for source in keys:
        title = layer_titles.get(source, source)
        lines.extend(_format_checklist_layer(title, by_source[source]))
        lines.append("")
    return lines


def _format_entities(entities: list[dict[str, str]]) -> list[str]:
    lines = [f"=== Deduped encoder entities ({len(entities)} item(s)) ==="]
    if not entities:
        lines.append("  (none)")
        return lines
    for i, row in enumerate(entities, 1):
        lines.append(
            f"  {i}. text={row.get('text', '')!r}  label={row.get('label', '')!r}"
        )
    return lines


def _format_coverage(coverage: dict) -> list[str]:
    lines = [
        "=== Coverage evaluation ===",
        f"  session_complete: {coverage.get('session_complete')}",
        f"  symptoms_complete: {coverage.get('symptoms_complete')}",
        f"  ready_for_disposition: {coverage.get('ready_for_disposition')}",
        f"  active_symptom_id: {coverage.get('active_symptom_id')!r}",
    ]
    instances = coverage.get("symptom_instances") or []
    lines.append(f"  symptom_instances ({len(instances)}):")
    if not instances:
        lines.append("    (none)")
    else:
        for inst in instances:
            lines.append(
                f"    - {inst['symptom_id']}: {inst['display_name']!r}"
            )
    missing = coverage.get("missing_slots") or []
    lines.append(f"  missing_slots ({len(missing)}):")
    if not missing:
        lines.append("    (none)")
    else:
        for m in missing:
            sid = m.get("symptom_id")
            suffix = f" @ {sid}" if sid else ""
            lines.append(f"    - {m.get('slot')}{suffix}")
    return lines


def _format_planner(
    *,
    question_mode: bool,
    next_question: str | None,
    question_reason: str | None,
    slot: str | None,
    bypass: bool,
) -> list[str]:
    lines = [
        "=== Question planner ===",
        f"  question_mode (natural): {question_mode}",
        f"  next_question: {next_question!r}",
        f"  question_reason: {question_reason!r}",
        f"  slot_being_asked: {slot!r}",
        f"  bypass_disposition: {bypass}",
    ]
    if bypass:
        lines.append(
            "  NOTE: Intake bypassed for this test — proceeding to retrieve_evidence "
            "regardless of coverage."
        )
    return lines


def _format_evidence(evidence: list) -> list[str]:
    from app.services.rag.chunk_and_ingest import brief_source_citation

    lines = [f"=== RAG retrieval ({len(evidence)} hit(s)) ==="]
    if not evidence:
        lines.append("  (none)")
        return lines
    for i, ev in enumerate(evidence, 1):
        brief = brief_source_citation(ev.source)
        lines.append(f"  --- {i} score={ev.score:.4f} source={brief} ---")
        lines.append(f"  {ev.snippet[:2000]}")
    return lines


# run full pipeline for one message; returns multi-line report for spreadsheet / stdout
def run_full_pipeline_trace(
    user_message: str,
    *,
    session_id: str = "full-test",
    bypass_intake: bool = True,
) -> str:
    """
    Execute chatbot nodes in order and assemble a step-by-step trace string.

    When ``bypass_intake`` is True, skips the question path and always runs
    retrieve → generate → policy (production disposition path).
    """
    from app.config import settings
    from app.orchestrator.coverage import coverage_intake_summary
    from app.orchestrator.nodes import (
        encode_input_node,
        evaluate_coverage_node,
        generate_draft_node,
        ingest_input_node,
        plan_question_node,
        policy_gate_node,
        preprocess_input_node,
        retrieve_evidence_node,
    )

    state: dict = {
        "session_id": session_id,
        "messages": [HumanMessage(content=user_message)],
        "clinical_checklist": [],
        "questions_asked": 0,
        "comorbidities_acknowledged": False,
    }

    sections: list[str] = [
        "=== FULL PIPELINE TEST ===",
        f"session_id: {session_id}",
        "",
        "=== Raw message ===",
        user_message,
        "",
    ]

    state = preprocess_input_node(state)  # type: ignore[arg-type]
    sections.extend(
        [
            "=== Preprocess ===",
            f"  normalized: {state['message_normalized']!r}",
            "",
        ]
    )

    state = ingest_input_node(state)  # type: ignore[arg-type]
    state = encode_input_node(state)  # type: ignore[arg-type]

    checklist = state.get("clinical_checklist") or []
    sections.extend(_format_checklist_by_source(checklist))
    sections.append("")
    entities = state.get("encoder_entities") or []
    sections.extend(_format_entities(entities))
    sections.extend(
        [
            "",
            f"rag_query (full message): {state['message_normalized']!r}",
        ]
    )
    sections.extend(
        [
            "",
            f"risk_hits (RISK_CATALOG): {state.get('risk_hits') or []}",
            f"encoder_embedding_dim: {len(state.get('encoder_pooled_embedding') or [])} "
            f"(expected {settings.encoder_embedding_dim})",
            "",
        ]
    )

    state = evaluate_coverage_node(state)  # type: ignore[arg-type]
    coverage = state.get("coverage") or {}
    sections.extend(_format_coverage(coverage))
    sections.append("")

    state = plan_question_node(state)  # type: ignore[arg-type]
    natural_mode = bool(state.get("question_mode"))
    natural_question = state.get("next_question")
    natural_reason = state.get("question_reason")
    natural_slot = state.get("slot_being_asked")

    if bypass_intake:
        state["question_mode"] = False

    sections.extend(
        _format_planner(
            question_mode=natural_mode,
            next_question=natural_question,
            question_reason=natural_reason,
            slot=natural_slot,
            bypass=bypass_intake,
        )
    )
    sections.append("")

    state = retrieve_evidence_node(state)  # type: ignore[arg-type]
    evidence = state.get("evidence") or []
    sections.extend(_format_evidence(evidence))
    sections.append("")

    state = generate_draft_node(state)  # type: ignore[arg-type]
    sections.extend(
        [
            "=== Generator (draft) ===",
            f"  intake_summary:\n{coverage_intake_summary(coverage)}",
            "",
            "  draft_response:",
            state.get("draft_response", ""),
            "",
        ]
    )

    state = policy_gate_node(state)  # type: ignore[arg-type]
    sections.extend(
        [
            "=== Policy gate ===",
            f"  escalated: {state.get('escalated')}",
            f"  safety_reason: {state.get('safety_reason')!r}",
            "",
            "=== Final response ===",
            state.get("final_response", ""),
        ]
    )
    return "\n".join(sections)


def _read_csv_rows(path: Path) -> tuple[list[list[str]], str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows, "utf-8-sig"


def _write_csv_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)


def _ensure_result_column(rows: list[list[str]]) -> None:
    if not rows:
        return
    header = rows[0]
    while len(header) <= _RESULT_COL:
        header.append("")
    if not header[_RESULT_COL].strip():
        header[_RESULT_COL] = "full_test_run"


def _warm_models() -> None:
    """Load encoder / GliNER once so batch rows reuse cached weights."""
    from app.config import settings
    from app.services.encoder import encode_user_message
    from app.services.gliner_ner import _get_gliner_model, gliner_configured
    from app.services.preprocess import normalize_user_text

    if settings.ner_load and settings.gliner_load and gliner_configured():
        _get_gliner_model()
    encode_user_message(normalize_user_text("warmup"))


def run_batch(
    csv_path: Path,
    *,
    first_row: int,
    last_row: int,
) -> int:
    """Run pipeline for Excel rows ``first_row``..``last_row`` (1-based); write column F."""
    _warm_models()
    rows, _ = _read_csv_rows(csv_path)
    if not rows:
        sys.stderr.write(f"Empty CSV: {csv_path}\n")
        return 1
    _ensure_result_column(rows)

    for excel_row in range(first_row, last_row + 1):
        data_idx = excel_row - 1
        if data_idx >= len(rows):
            sys.stderr.write(f"Row {excel_row} out of range.\n")
            return 1
        while len(rows[data_idx]) <= _QUERY_COL:
            rows[data_idx].append("")
        query = rows[data_idx][_QUERY_COL].strip()
        if not query:
            sys.stderr.write(f"Row {excel_row}: empty query in column B.\n")
            continue
        source = rows[data_idx][0] if rows[data_idx] else f"row{excel_row}"
        print(f"Processing row {excel_row} ({source})...", flush=True)
        report = run_full_pipeline_trace(
            query,
            session_id=f"full-test-{excel_row}",
            bypass_intake=True,
        )
        while len(rows[data_idx]) <= _RESULT_COL:
            rows[data_idx].append("")
        rows[data_idx][_RESULT_COL] = report
        _write_csv_rows(csv_path, rows)
        print(f"Row {excel_row} done ({len(report)} chars written to column F).", flush=True)

    print(f"Wrote column F (rows {first_row}-{last_row}) to {csv_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Full chatbot pipeline trace (intake bypass → RAG → generate).",
    )
    parser.add_argument(
        "-m",
        "--message",
        default="",
        help="Single user message (if set, ignores --batch)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process vignette CSV column B rows 2-11 → column F",
    )
    parser.add_argument("--csv", type=Path, default=_DEFAULT_CSV)
    parser.add_argument("--first-row", type=int, default=2)
    parser.add_argument("--last-row", type=int, default=11)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    _configure_logging(verbose=args.verbose)

    os.environ.setdefault("TRI_BACK_LOAD_RAG", "1")
    os.environ.setdefault("TRI_BACK_LOAD_NER", "1")
    # Keep batch stable/safe on CPU-only runs: use deterministic fallback generator.
    os.environ.setdefault("TRI_BACK_GENERATOR_DIR", "__fulltest_no_generator__")

    if args.message.strip():
        report = run_full_pipeline_trace(args.message.strip())
        sys.stdout.write(report + "\n")
        return 0

    if args.batch or not args.message.strip():
        if not args.csv.is_file():
            sys.stderr.write(f"CSV not found: {args.csv}\n")
            return 1
        return run_batch(
            args.csv,
            first_row=args.first_row,
            last_row=args.last_row,
        )

    sys.stderr.write("Provide -m/--message or --batch.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
