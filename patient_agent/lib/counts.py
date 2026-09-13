"""PRISMA-style count audit for MedQA screening runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class StageCount:
    name: str
    n_in: int
    n_out: int
    dropped: int
    drop_reasons: dict[str, int] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GridCell:
    family: str
    auto_n: int = 0
    clinician_n: int | None = None
    sampled_n: int = 0
    status: str = "pending"  # pending | filled | unknown

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScreeningAudit:
    run_id: str
    started_at: str
    corpus: str
    source_detail: str
    seed: int
    protocol: str = "references/dataset_screening.md"
    stages: list[StageCount] = field(default_factory=list)
    grid: dict[str, GridCell] = field(default_factory=dict)
    clinician_eligible: str | int = "pending"
    clinician_excluded: int | None = None
    clinician_blank: int | None = None
    sampled: int | None = None
    n_before_dedupe: int | None = None
    n_duplicates_dropped: int = 0
    split_counts_raw: dict[str, int] = field(default_factory=dict)
    split_counts_auto_eligible: dict[str, int] = field(default_factory=dict)
    lexicon_term_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def add_stage(
        self,
        name: str,
        n_in: int,
        n_out: int,
        drop_reasons: dict[str, int] | None = None,
        notes: str = "",
    ) -> StageCount:
        dropped = n_in - n_out
        drop_reasons = drop_reasons or {}
        reason_sum = sum(drop_reasons.values())
        if reason_sum != dropped:
            raise ValueError(
                f"stage {name!r}: drop_reasons sum {reason_sum} != dropped {dropped} "
                f"(n_in={n_in}, n_out={n_out}, reasons={drop_reasons})"
            )
        stage = StageCount(
            name=name,
            n_in=n_in,
            n_out=n_out,
            dropped=dropped,
            drop_reasons=drop_reasons or {},
            notes=notes,
        )
        self.stages.append(stage)
        return stage

    def finalize_grid(self) -> None:
        for cell in self.grid.values():
            n = cell.clinician_n if cell.clinician_n is not None else cell.auto_n
            if cell.sampled_n > 0:
                cell.status = "filled"
            elif n == 0:
                cell.status = "unknown"
            else:
                cell.status = "pending_sample"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "corpus": self.corpus,
            "source_detail": self.source_detail,
            "seed": self.seed,
            "protocol": self.protocol,
            "stages": [s.to_dict() for s in self.stages],
            "grid": {k: v.to_dict() for k, v in self.grid.items()},
            "clinician_eligible": self.clinician_eligible,
            "clinician_excluded": self.clinician_excluded,
            "clinician_blank": self.clinician_blank,
            "sampled": self.sampled,
            "n_before_dedupe": self.n_before_dedupe,
            "n_duplicates_dropped": self.n_duplicates_dropped,
            "split_counts_raw": self.split_counts_raw,
            "split_counts_auto_eligible": self.split_counts_auto_eligible,
            "lexicon_term_counts": self.lexicon_term_counts,
            "notes": self.notes,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    def write_markdown(self, path: Path) -> None:
        lines = [
            f"# Screening audit `{self.run_id}`",
            "",
            f"- Started: {self.started_at}",
            f"- Corpus: `{self.corpus}`",
            f"- Source: {self.source_detail}",
            f"- Seed: {self.seed}",
            f"- Protocol: {self.protocol}",
            "",
            "## Stages",
            "",
            "| Stage | N in | N out | Dropped | Drop reasons |",
            "|---|---:|---:|---:|---|",
        ]
        for s in self.stages:
            reasons = ", ".join(f"{k}={v}" for k, v in sorted(s.drop_reasons.items())) or "—"
            lines.append(
                f"| {s.name} | {s.n_in} | {s.n_out} | {s.dropped} | {reasons} |"
            )
        lines += [
            "",
            f"Duplicates dropped (stem hash): **{self.n_duplicates_dropped}**",
            f"Clinician eligible: **{self.clinician_eligible}**",
            f"Clinician excluded: **{self.clinician_excluded}**",
            f"Clinician blank (pending): **{self.clinician_blank}**",
            f"Sampled: **{self.sampled}**",
            "",
            "## Grid (auto preview until Stage 3)",
            "",
            "| Red-flag family | Auto N | Clinician N | Sampled | Status |",
            "|---|---:|---:|---:|---|",
        ]
        for fam, cell in self.grid.items():
            clin = "—" if cell.clinician_n is None else str(cell.clinician_n)
            lines.append(
                f"| {fam} | {cell.auto_n} | {clin} | {cell.sampled_n} | {cell.status} |"
            )
        if self.split_counts_raw:
            lines += ["", "## Splits (raw unique items)", ""]
            for k, v in sorted(self.split_counts_raw.items()):
                elig = self.split_counts_auto_eligible.get(k, 0)
                lines.append(f"- `{k}`: raw {v}, auto-eligible {elig}")
        if self.lexicon_term_counts:
            lines += ["", "## Lexicon term hits (an item may match several terms)", ""]
            for k, v in sorted(self.lexicon_term_counts.items(), key=lambda kv: (-kv[1], kv[0])):
                lines.append(f"- `{k}`: {v}")
        if self.notes:
            lines += ["", "## Notes", ""]
            lines.extend(f"- {n}" for n in self.notes)
        lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")


def new_audit(*, corpus: str, source_detail: str, seed: int) -> ScreeningAudit:
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    from lib.lexicon import GRID_FAMILIES

    grid = {fam: GridCell(family=fam) for fam in GRID_FAMILIES}
    grid["unknown"] = GridCell(family="unknown")
    return ScreeningAudit(
        run_id=run_id,
        started_at=now.isoformat(),
        corpus=corpus,
        source_detail=source_detail,
        seed=seed,
        grid=grid,
    )
