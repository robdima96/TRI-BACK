"""CLI: screen MedQA-US for LBP-eligible case vignettes and write a count audit.

Examples (from the patient_agent directory):

  python screen_medqa.py --source hf
  python screen_medqa.py --source jsonl --path data/raw/medqa.jsonl
  python screen_medqa.py --source agentclinic --path data/raw/agentclinic_medqa.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.cards import from_agentclinic_osce, from_medqa_stem, write_card
from lib.counts import new_audit
from lib.load_medqa import iter_unique, load_huggingface_medqa, load_medqa_jsonl
from lib.screen import screen_items, stratified_sample, write_all_rows_jsonl, write_review_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen MedQA-US for LBP OSCE candidates.")
    parser.add_argument(
        "--source",
        choices=("hf", "jsonl", "agentclinic"),
        default="hf",
        help="hf = GBaker/MedQA-USMLE-4-options; jsonl = native MedQA jsonl; agentclinic = OSCE jsonl",
    )
    parser.add_argument("--path", type=Path, default=None, help="Local jsonl for jsonl/agentclinic")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-n", type=int, default=20)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs" / "screening",
        help="Directory for audit JSON/MD, review CSV, and provisional cards",
    )
    args = parser.parse_args()

    if args.source == "hf":
        items, detail = load_huggingface_medqa()
        corpus = "medqa_us"
    elif args.source in {"jsonl", "agentclinic"}:
        if not args.path:
            print("--path is required for jsonl/agentclinic", file=sys.stderr)
            return 2
        items = load_medqa_jsonl(args.path, split=args.source)
        detail = f"local {args.source} {args.path} n={len(items)}"
        corpus = "medqa_us"
    else:
        return 2

    audit = new_audit(corpus=corpus, source_detail=detail, seed=args.seed)
    n_loaded = len(items)
    items = iter_unique(items)
    audit.n_before_dedupe = n_loaded
    audit.n_duplicates_dropped = n_loaded - len(items)
    if audit.n_duplicates_dropped:
        audit.add_stage(
            "stem_hash_dedupe",
            n_in=n_loaded,
            n_out=len(items),
            drop_reasons={"duplicate_stem_hash": audit.n_duplicates_dropped},
            notes="first occurrence kept",
        )
    rows, survivors = screen_items(items, audit)
    sampled = stratified_sample(survivors, audit, n=args.sample_n, seed=args.seed)
    audit.finalize_grid()

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    run = audit.run_id
    audit.write(out / f"audit_{run}.json")
    audit.write_markdown(out / f"audit_{run}.md")
    write_review_csv(rows, out / f"clinician_review_{run}.csv")
    write_all_rows_jsonl(rows, out / f"all_rows_{run}.jsonl")

    raw_stage = next((s for s in audit.stages if s.name == "raw"), None)
    (out / "LATEST.txt").write_text(
        "\n".join(
            [
                f"run_id={run}",
                f"corpus={corpus}",
                f"source={detail}",
                f"n_before_dedupe={audit.n_before_dedupe}",
                f"n_duplicates_dropped={audit.n_duplicates_dropped}",
                f"raw_unique={raw_stage.n_out if raw_stage else '?'}",
                f"auto_eligible={len(survivors)}",
                f"provisional_sample={len(sampled)}",
                f"clinician_eligible={audit.clinician_eligible}",
                f"audit_json=audit_{run}.json",
                f"audit_md=audit_{run}.md",
                f"clinician_csv=clinician_review_{run}.csv",
                f"all_rows=all_rows_{run}.jsonl",
                f"sample_manifest=sample_manifest_{run}.json",
                "",
            ]
        ),
        encoding="utf-8",
    )

    cards_dir = ROOT / "outputs" / "cards" / run
    by_id = {item.source_id: item for item in survivors}
    sample_manifest: list[dict] = []
    for item in sampled:
        item = by_id.get(item.source_id, item)
        if item.agentclinic_osce:
            card = from_agentclinic_osce(
                item.agentclinic_osce,
                source_id=item.source_id,
                stem_hash=item.stem_hash,
            )
        else:
            card = from_medqa_stem(
                question=item.question,
                answer=item.answer,
                source_id=item.source_id,
                stem_hash=item.stem_hash,
            )
        write_card(card, cards_dir / f"{card['case_id']}.json")
        sample_manifest.append(
            {
                "case_id": card["case_id"],
                "source_id": item.source_id,
                "stem_hash": item.stem_hash,
                "split": item.split,
                "auto_red_flag_family": next(
                    (r.auto_red_flag_family for r in rows if r.source_id == item.source_id),
                    None,
                ),
                "has_agentclinic_osce": item.agentclinic_osce is not None,
                "conversion": card.get("conversion", "from_agentclinic_osce"),
            }
        )
    (out / f"sample_manifest_{run}.json").write_text(
        json.dumps(
            {
                "run_id": run,
                "seed": args.seed,
                "n": len(sample_manifest),
                "note": "Provisional pre-clinician sample. IDs and hashes only; stems live in clinician_review CSV.",
                "items": sample_manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(audit.to_dict(), indent=2))
    print(f"\nWrote audit -> {out / f'audit_{run}.md'}")
    print(f"Clinician review CSV -> {out / f'clinician_review_{run}.csv'}")
    print(f"Provisional cards -> {cards_dir} ({len(sampled)} files)")
    print("Stage 3 (clinician_include) is still pending - sample is provisional.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
