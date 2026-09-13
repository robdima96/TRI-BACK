"""Load MedQA-US items and optional AgentClinic MedQA OSCE JSONL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class MedQAItem:
    source_id: str
    split: str
    question: str
    options_text: str
    answer: str
    meta: dict[str, Any] = field(default_factory=dict)
    agentclinic_osce: dict[str, Any] | None = None

    @property
    def search_text(self) -> str:
        parts = [self.question, self.options_text, self.answer]
        osce = self.agentclinic_osce
        if osce:
            exam = osce.get("OSCE_Examination") or osce
            actor = exam.get("Patient_Actor") or {}
            parts.extend(
                [
                    str(exam.get("Objective_for_Doctor") or ""),
                    str(actor.get("History") or ""),
                    str((actor.get("Symptoms") or {}).get("Primary_Symptom") or ""),
                    str(exam.get("Correct_Diagnosis") or ""),
                ]
            )
        return " ".join(p for p in parts if p)

    @property
    def stem_text(self) -> str:
        """Patient-facing stem only. Do not use MCQ options for vignette/family/cervical filters."""
        parts = [self.question]
        osce = self.agentclinic_osce
        if osce:
            exam = osce.get("OSCE_Examination") or osce
            actor = exam.get("Patient_Actor") or {}
            parts.extend(
                [
                    str(exam.get("Objective_for_Doctor") or ""),
                    str(actor.get("History") or ""),
                    str((actor.get("Symptoms") or {}).get("Primary_Symptom") or ""),
                ]
            )
        return " ".join(p for p in parts if p)

    @property
    def stem_hash(self) -> str:
        return hashlib.sha256(self.question.strip().encode("utf-8")).hexdigest()[:16]

    def has_osce_history(self) -> bool:
        if not self.agentclinic_osce:
            return False
        exam = self.agentclinic_osce.get("OSCE_Examination") or self.agentclinic_osce
        actor = exam.get("Patient_Actor") or {}
        return bool(str(actor.get("History") or "").strip())


def _options_to_text(options: Any) -> str:
    if options is None:
        return ""
    if isinstance(options, dict):
        return " ".join(f"{k}: {v}" for k, v in options.items())
    if isinstance(options, list):
        return " ".join(str(x) for x in options)
    return str(options)


def load_medqa_jsonl(path: Path, *, split: str = "unknown") -> list[MedQAItem]:
    items: list[MedQAItem] = []
    with path.open(encoding="utf-8") as handle:
        for i, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "OSCE_Examination" in row:
                items.append(_from_agentclinic(row, index=i, split=split))
                continue
            question = str(row.get("question") or row.get("Question") or "")
            options = row.get("options") or {
                "A": row.get("opa") or row.get("A"),
                "B": row.get("opb") or row.get("B"),
                "C": row.get("opc") or row.get("C"),
                "D": row.get("opd") or row.get("D"),
                "E": row.get("ope") or row.get("E"),
            }
            options = {k: v for k, v in options.items() if v}
            answer = str(row.get("answer") or row.get("Answer") or row.get("answer_idx") or "")
            source_id = str(row.get("id") or row.get("qid") or f"{path.stem}:{i}")
            items.append(
                MedQAItem(
                    source_id=source_id,
                    split=str(row.get("meta_info") or split),
                    question=question,
                    options_text=_options_to_text(options),
                    answer=answer,
                    meta={k: v for k, v in row.items() if k not in {"question", "options"}},
                )
            )
    return items


def _from_agentclinic(row: dict[str, Any], *, index: int, split: str) -> MedQAItem:
    exam = row.get("OSCE_Examination") or {}
    actor = exam.get("Patient_Actor") or {}
    hist = str(actor.get("History") or "")
    demo = str(actor.get("Demographics") or "")
    question = f"{demo}. {hist}".strip()
    diagnosis = str(exam.get("Correct_Diagnosis") or "")
    return MedQAItem(
        source_id=f"agentclinic_medqa:{index}",
        split=split,
        question=question,
        options_text="",
        answer=diagnosis,
        meta={"objective": exam.get("Objective_for_Doctor")},
        agentclinic_osce=row,
    )


def load_huggingface_medqa() -> tuple[list[MedQAItem], str]:
    """Load English MedQA-US (official train + validation + test, ~12,723 items).

    Prefer `awinml/medqa` config `questions` (Jin et al. splits). Fall back to
    `GBaker/MedQA-USMLE-4-options`, which has train+test only (no validation).
    """
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError(
            "Install datasets to load MedQA from Hugging Face: pip install datasets"
        ) from exc

    source_name = "awinml/medqa"
    try:
        ds = load_dataset("awinml/medqa", "questions")
    except Exception:
        source_name = "GBaker/MedQA-USMLE-4-options"
        ds = load_dataset(source_name)

    items: list[MedQAItem] = []
    for split_name, split in ds.items():
        for i, row in enumerate(split):
            options = row.get("options") or {}
            items.append(
                MedQAItem(
                    source_id=str(row.get("id") or f"{source_name}:{split_name}:{i}"),
                    split=split_name,
                    question=str(row.get("question") or ""),
                    options_text=_options_to_text(options),
                    answer=str(row.get("answer") or ""),
                    meta={"hf_split": split_name, "hf_source": source_name},
                )
            )
    splits = list(ds.keys())
    detail = f"HuggingFace {source_name} splits={splits} n={len(items)}"
    if "validation" not in splits and "dev" not in splits:
        detail += " [WARNING: no validation/dev split in this copy]"
    return items, detail


def iter_unique(items: Iterable[MedQAItem]) -> list[MedQAItem]:
    """Dedupe by stem hash, keeping the first occurrence."""
    seen: set[str] = set()
    out: list[MedQAItem] = []
    for item in items:
        key = item.stem_hash
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
