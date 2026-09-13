"""Apply Stage 3 clinician coding and re-sample (Stage 4).

Fill clinician_include with yes/no on the review CSV, then:

  python apply_clinician.py --review outputs/screening/clinician_review_<run>.csv --prior-audit outputs/screening/audit_<run>.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.counts import ScreeningAudit, StageCount, new_audit
from lib.load_medqa import MedQAItem
from lib.screen import stratified_sample


def _yes(value: str) -> bool:
    return value.strip().lower() in {"yes", "y", "include", "true", "1"}


def _no(value: str) -> bool:
    return value.strip().lower() in {"no", "n", "exclude", "false", "0"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply clinician include/exclude and re-sample.")
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--prior-audit", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-n", type=int, default=20)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "screening")
    args = parser.parse_args()

    with args.review.open(encoding="utf-8", newline="") as handle:
        coded = list(csv.DictReader(handle))

    yes_rows = [r for r in coded if _yes(r.get("clinician_include") or "")]
    no_rows = [r for r in coded if _no(r.get("clinician_include") or "")]
    blank_rows = [r for r in coded if not (r.get("clinician_include") or "").strip()]

    prior = {}
    if args.prior_audit and args.prior_audit.is_file():
        prior = json.loads(args.prior_audit.read_text(encoding="utf-8"))

    audit = new_audit(
        corpus=prior.get("corpus", "medqa_us"),
        source_detail=f"clinician coding of {args.review.name}",
        seed=args.seed,
    )
    if prior.get("stages"):
        for s in prior["stages"]:
            audit.stages.append(
                StageCount(
                    name=s["name"],
                    n_in=s["n_in"],
                    n_out=s["n_out"],
                    dropped=s["dropped"],
                    drop_reasons=s.get("drop_reasons") or {},
                    notes=s.get("notes") or "",
                )
            )
        audit.n_before_dedupe = prior.get("n_before_dedupe")
        audit.n_duplicates_dropped = prior.get("n_duplicates_dropped") or 0
        audit.split_counts_raw = prior.get("split_counts_raw") or {}
        audit.split_counts_auto_eligible = prior.get("split_counts_auto_eligible") or {}
        audit.lexicon_term_counts = prior.get("lexicon_term_counts") or {}

    audit.add_stage(
        "clinician_review",
        n_in=len(coded),
        n_out=len(yes_rows),
        drop_reasons={
            "clinician_exclude": len(no_rows),
            "clinician_blank_pending": len(blank_rows),
        },
        notes="clinician_include yes/no on auto-eligible sheet",
    )

    if blank_rows and not yes_rows:
        audit.clinician_eligible = "pending"
        audit.clinician_excluded = len(no_rows)
        audit.clinician_blank = len(blank_rows)
        audit.notes.append("No clinician includes yet — fill clinician_include and re-run.")
        audit.sampled = None
    else:
        audit.clinician_eligible = len(yes_rows)
        audit.clinician_excluded = len(no_rows)
        audit.clinician_blank = len(blank_rows)
        family_counts: Counter[str] = Counter()
        survivors: list[MedQAItem] = []
        for row in yes_rows:
            fam = (row.get("clinician_grid") or "").strip() or (row.get("auto_red_flag_family") or "unknown")
            if fam not in audit.grid:
                fam = "unknown"
            family_counts[fam] += 1
            survivors.append(
                MedQAItem(
                    source_id=row["source_id"],
                    split=row.get("split") or "",
                    question=row.get("question") or "",
                    options_text="",
                    answer=row.get("answer") or "",
                    meta={
                        "grid_family": fam if fam in audit.grid else "unknown",
                    },
                )
            )
        for fam in list(audit.grid):
            audit.grid[fam].clinician_n = family_counts.get(fam, 0)
            audit.grid[fam].auto_n = (prior.get("grid") or {}).get(fam, {}).get("auto_n", 0)
        sampled = stratified_sample(survivors, audit, n=args.sample_n, seed=args.seed)
        audit.finalize_grid()
        audit.notes.append(
            f"Stage 4 sample n={len(sampled)} from clinician-eligible N={len(yes_rows)}. "
            "Empty grid cells remain unknown."
        )

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    run = audit.run_id
    audit.write(out / f"audit_{run}.json")
    audit.write_markdown(out / f"audit_{run}.md")
    print(json.dumps(audit.to_dict(), indent=2))
    print(f"Wrote {out / f'audit_{run}.md'}")
    if blank_rows:
        print(f"WARNING: {len(blank_rows)} rows still blank (pending).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
