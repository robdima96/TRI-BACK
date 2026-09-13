"""Stage MedQA items through the pre-registered LBP screen."""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lib.counts import ScreeningAudit
from lib.lexicon import (
    is_cervical_only,
    is_isolated_radiology,
    is_lumbar_puncture_only,
    is_vignette,
    lexicon_hit,
    preview_red_flag_family,
    token_count,
)
from lib.load_medqa import MedQAItem


@dataclass
class ScreenedRow:
    source_id: str
    stem_hash: str
    split: str
    stage_passed: str
    drop_reason: str | None
    lexicon_terms: list[str]
    auto_red_flag_family: str
    token_count: int
    has_agentclinic_osce: bool
    question: str
    answer: str
    clinician_include: str = ""
    clinician_grid: str = ""
    clinician_notes: str = ""

    def to_csv_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lexicon_terms"] = "|".join(self.lexicon_terms)
        return d


def screen_items(
    items: list[MedQAItem],
    audit: ScreeningAudit,
) -> tuple[list[ScreenedRow], list[MedQAItem]]:
    """Run Stages 1–2b. Returns all tracked rows plus items that survive to clinician review."""

    n_raw = len(items)
    audit.split_counts_raw = dict(Counter(i.split for i in items))
    audit.add_stage("raw", n_in=n_raw, n_out=n_raw, notes="loaded unique items after stem-hash dedupe")

    rows: list[ScreenedRow] = []
    after_lex: list[MedQAItem] = []
    drop_lex: Counter[str] = Counter()
    term_counts: Counter[str] = Counter()

    for item in items:
        text = item.search_text
        hit = lexicon_hit(text)
        if not hit.matched:
            drop_lex["no_lexicon_hit"] += 1
            rows.append(_row(item, "raw", "no_lexicon_hit", hit.terms, text))
            continue
        for term in hit.terms:
            term_counts[term] += 1
        if is_lumbar_puncture_only(text, hit.terms):
            drop_lex["lumbar_puncture_only"] += 1
            rows.append(_row(item, "lexical", "lumbar_puncture_only", hit.terms, text))
            continue
        after_lex.append(item)
        rows.append(_row(item, "lexical", None, hit.terms, text))

    audit.lexicon_term_counts = dict(term_counts)

    audit.add_stage(
        "lexical",
        n_in=n_raw,
        n_out=len(after_lex),
        drop_reasons=dict(drop_lex),
        notes="high-recall LBP lexicon; 1b drops lumbar-puncture-only",
    )

    after_vig: list[MedQAItem] = []
    drop_vig: Counter[str] = Counter()
    for item in after_lex:
        text = item.stem_text
        if item.has_osce_history():
            after_vig.append(item)
            _update_stage(rows, item, "vignette", None)
            continue
        ok, reason = is_vignette(text)
        if not ok:
            if is_isolated_radiology(text):
                drop_vig["isolated_radiology"] += 1
                _update_stage(rows, item, "lexical", "isolated_radiology")
            else:
                drop_vig[reason or "not_vignette"] += 1
                _update_stage(rows, item, "lexical", reason)
            continue
        after_vig.append(item)
        _update_stage(rows, item, "vignette", None)

    audit.add_stage(
        "vignette_heuristic",
        n_in=len(after_lex),
        n_out=len(after_vig),
        drop_reasons=dict(drop_vig),
        notes="age + presentation cues; AgentClinic OSCE history counts as vignette",
    )

    after_cx: list[MedQAItem] = []
    drop_cx: Counter[str] = Counter()
    for item in after_vig:
        if is_cervical_only(item.stem_text):
            drop_cx["cervical_only"] += 1
            _update_stage(rows, item, "vignette", "cervical_only")
            continue
        after_cx.append(item)
        _update_stage(rows, item, "auto_eligible", None)

    audit.add_stage(
        "auto_cervical_only",
        n_in=len(after_vig),
        n_out=len(after_cx),
        drop_reasons=dict(drop_cx),
        notes="neck/cervical without lumbar-region terms",
    )

    family_counts: Counter[str] = Counter()
    for item in after_cx:
        fam = preview_red_flag_family(item.stem_text)
        family_counts[fam] += 1

    for fam in list(audit.grid):
        audit.grid[fam].auto_n = family_counts.get(fam, 0)
        if audit.grid[fam].auto_n == 0:
            audit.grid[fam].status = "unknown"
        else:
            audit.grid[fam].status = "pending_clinician"

    audit.notes.append(
        "Stage 3 clinician_eligible is pending until clinician_review.csv is filled "
        "(yes/no in clinician_include). Run apply_clinician.py after coding."
    )
    audit.clinician_eligible = "pending"
    audit.clinician_blank = len(after_cx)
    audit.sampled = None
    audit.split_counts_auto_eligible = dict(Counter(i.split for i in after_cx))
    return rows, after_cx


def stratified_sample(
    survivors: list[MedQAItem],
    audit: ScreeningAudit,
    *,
    n: int = 20,
    seed: int = 42,
) -> list[MedQAItem]:
    """Sample up to n items, spreading across auto red-flag families. Empty families stay unknown."""
    rng = random.Random(seed)
    buckets: dict[str, list[MedQAItem]] = {fam: [] for fam in audit.grid}
    for item in survivors:
        fam = str(item.meta.get("grid_family") or "") or preview_red_flag_family(item.stem_text)
        buckets.setdefault(fam, []).append(item)

    chosen: list[MedQAItem] = []
    families_with_items = [f for f, items in buckets.items() if items]
    if not families_with_items:
        audit.sampled = 0
        return []

    # Round-robin so rare families are not wiped out by mechanical LBP.
    idxs = {f: 0 for f in families_with_items}
    for fam in families_with_items:
        rng.shuffle(buckets[fam])

    while len(chosen) < min(n, len(survivors)):
        progressed = False
        for fam in families_with_items:
            if len(chosen) >= n:
                break
            bucket = buckets[fam]
            i = idxs[fam]
            if i < len(bucket):
                chosen.append(bucket[i])
                idxs[fam] = i + 1
                audit.grid[fam].sampled_n += 1
                audit.grid[fam].status = "filled"
                progressed = True
        if not progressed:
            break

    for fam, cell in audit.grid.items():
        if cell.sampled_n == 0:
            cell.status = "unknown"

    audit.sampled = len(chosen)
    audit.notes.append(
        f"Provisional sample n={len(chosen)} from auto-eligible (pre-clinician). "
        "Replace after Stage 3."
    )
    return chosen


def write_review_csv(rows: list[ScreenedRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = [r for r in rows if r.stage_passed == "auto_eligible"]
    fields = [
        "source_id",
        "stem_hash",
        "split",
        "auto_red_flag_family",
        "lexicon_terms",
        "token_count",
        "has_agentclinic_osce",
        "question",
        "answer",
        "clinician_include",
        "clinician_grid",
        "clinician_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in keep:
            writer.writerow({k: row.to_csv_dict()[k] for k in fields})


def write_all_rows_jsonl(rows: list[ScreenedRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_csv_dict(), ensure_ascii=False) + "\n")


def _row(
    item: MedQAItem,
    stage: str,
    drop: str | None,
    terms: list[str],
    text: str,
) -> ScreenedRow:
    return ScreenedRow(
        source_id=item.source_id,
        stem_hash=item.stem_hash,
        split=item.split,
        stage_passed=stage,
        drop_reason=drop,
        lexicon_terms=terms,
        auto_red_flag_family=preview_red_flag_family(item.stem_text) if terms else "unknown",
        token_count=token_count(item.question),
        has_agentclinic_osce=item.agentclinic_osce is not None,
        question=item.question,
        answer=item.answer,
    )


def _update_stage(
    rows: list[ScreenedRow], item: MedQAItem, stage: str, drop: str | None
) -> None:
    for row in reversed(rows):
        if row.source_id == item.source_id and row.stem_hash == item.stem_hash:
            row.stage_passed = stage
            row.drop_reason = drop
            return
