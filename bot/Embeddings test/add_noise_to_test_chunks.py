"""Progressively add random English noise to the vignette in ``test_chunks.csv`` cell B2.

Reads ``chunk_string`` from row 2 (Excel B2), applies 19 cumulative noise steps with
Gaussian-scaled insertion counts, and writes results to rows 3–21 (Excel B3–B21).
Row 21 is the noisiest.

Run from repo root::

    python "Embeddings test/add_noise_to_test_chunks.py"
    python "Embeddings test/add_noise_to_test_chunks.py" --seed 42
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent
_DEFAULT_CSV = _ROOT / "test_chunks.csv"

# Excel row 2 = first data row after header; B3–B21 = 19 noise steps.
_SOURCE_EXCEL_ROW = 2
_FIRST_NOISY_EXCEL_ROW = 3
_LAST_NOISY_EXCEL_ROW = 21
_NUM_STEPS = _LAST_NOISY_EXCEL_ROW - _FIRST_NOISY_EXCEL_ROW + 1

# Short English fragments used as "noise" (generic + loosely clinical filler).
_NOISE_FRAGMENTS: tuple[str, ...] = (
    "I went to the store yesterday afternoon.",
    "The weather has been unusually warm this week.",
    "My cousin called about dinner plans for Saturday.",
    "I need to pick up milk and bread on the way home.",
    "The bus was late again this morning.",
    "I watched a documentary about gardening last night.",
    "My phone battery died before I could reply.",
    "We are thinking about repainting the kitchen soon.",
    "The cat knocked a glass off the counter.",
    "I forgot to water the plants on the balcony.",
    "Traffic on the highway was terrible after work.",
    "I have been reading a novel about travel in Italy.",
    "The meeting ran longer than I expected.",
    "My neighbor mentioned the street fair next month.",
    "I tried a new recipe for soup on Sunday.",
    "The printer at the office jammed again.",
    "I walked around the park for about twenty minutes.",
    "My sister sent photos from her vacation.",
    "I stayed up too late scrolling on my tablet.",
    "The grocery store was out of the brand I usually buy.",
    "I sometimes get headaches when I skip breakfast.",
    "My knees ache a little after long walks.",
    "I have not been sleeping well lately anyway.",
    "I mentioned this to a friend at coffee yesterday.",
    "The appointment reminder popped up on my calendar.",
    "I feel tired in the afternoons most days.",
    "I took some over-the-counter pain relief last week.",
    "My doctor said to keep monitoring things generally.",
    "I wonder if stress at work is part of it.",
    "I have had similar discomfort off and on before.",
    "Physical therapy helped my shoulder last year.",
    "I am trying to stretch more in the mornings.",
    "Insurance paperwork took forever to sort out.",
    "I booked a follow-up just to be safe.",
    "The waiting room was crowded when I arrived.",
    "I filled out another form at the front desk.",
)


def _insert_fragment(text: str, fragment: str, rng: random.Random) -> str:
    fragment = fragment.strip()
    if not fragment:
        return text
    if not text.strip():
        return fragment
    # Insert at a random word boundary or at start/end (always spaced).
    words = text.split()
    if len(words) <= 1:
        positions = [0, len(text)]
    else:
        positions = [0]
        offset = 0
        for w in words[:-1]:
            offset += len(w) + 1
            positions.append(offset)
        positions.append(len(text))
    pos = rng.choice(positions)
    if pos == 0:
        return f"{fragment} {text}".strip()
    if pos >= len(text):
        return f"{text} {fragment}".strip()
    before, after = text[:pos].rstrip(), text[pos:].lstrip()
    return f"{before} {fragment} {after}".strip()


def _apply_noise_step(
    text: str,
    *,
    step: int,
    num_steps: int,
    rng: random.Random,
    rng_gauss: np.random.Generator,
) -> str:
    """One noise step; ``step`` is 1 .. ``num_steps`` (higher = more noise)."""
    t = step / num_steps
    # Gaussian number of insertions; mean/variance rise with step index.
    mu = 1.0 + 4.5 * t
    sigma = 0.4 + 1.0 * t
    n_insert = int(max(1, round(rng_gauss.normal(loc=mu, scale=sigma))))
    n_insert = min(n_insert, 14)

    out = text
    pool = list(_NOISE_FRAGMENTS)
    for _ in range(n_insert):
        fragment = rng.choice(pool)
        out = _insert_fragment(out, fragment, rng)

    # Occasional light word-level perturbation at higher noise levels.
    if t >= 0.35 and rng.random() < 0.15 * t:
        words = out.split()
        if len(words) > 4:
            i = rng.randrange(len(words))
            words[i] = rng.choice(
                ("actually", "maybe", "sometimes", "often", "really", "just")
            )
            out = " ".join(words)

    out = re.sub(r"\s+", " ", out).strip()
    return out


def build_noisy_progression(
    base: str,
    *,
    num_steps: int = _NUM_STEPS,
    seed: int | None = None,
) -> list[str]:
    """Return ``num_steps`` strings; last entry is the noisiest."""
    if seed is not None:
        rng = random.Random(seed)
        rng_gauss = np.random.default_rng(seed)
    else:
        rng = random.Random()
        rng_gauss = np.random.default_rng()

    versions: list[str] = []
    current = base.strip()
    for step in range(1, num_steps + 1):
        current = _apply_noise_step(
            current,
            step=step,
            num_steps=num_steps,
            rng=rng,
            rng_gauss=rng_gauss,
        )
        versions.append(current)
    return versions


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [{k: (row.get(k) or "") for k in fieldnames} for row in reader]
    if "chunk_string" not in fieldnames:
        raise ValueError(f"CSV missing chunk_string column: {path}")
    return fieldnames, rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


def update_test_chunks_csv(
    csv_path: Path,
    *,
    seed: int | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Fill Excel B3–B21 from B2; return the 19 noisy strings."""
    fieldnames, rows = _read_csv(csv_path)

    # Excel row N -> zero-based data index N - 2 (row 1 = header).
    source_idx = _SOURCE_EXCEL_ROW - 2
    first_idx = _FIRST_NOISY_EXCEL_ROW - 2
    last_idx = _LAST_NOISY_EXCEL_ROW - 2

    if source_idx < 0 or source_idx >= len(rows):
        raise IndexError(f"Source row Excel B{_SOURCE_EXCEL_ROW} missing in {csv_path}")
    if last_idx >= len(rows):
        raise IndexError(
            f"Need Excel rows B{_FIRST_NOISY_EXCEL_ROW}–B{_LAST_NOISY_EXCEL_ROW}; "
            f"CSV has only {len(rows)} data row(s)"
        )

    base = rows[source_idx].get("chunk_string", "").strip()
    if not base:
        raise ValueError(
            f"chunk_string empty at Excel B{_SOURCE_EXCEL_ROW} ({csv_path})"
        )

    noisy = build_noisy_progression(base, num_steps=_NUM_STEPS, seed=seed)
    if len(noisy) != _NUM_STEPS:
        raise RuntimeError(f"expected {_NUM_STEPS} noisy versions, got {len(noisy)}")

    for offset, text in enumerate(noisy):
        rows[first_idx + offset]["chunk_string"] = text

    if not dry_run:
        _write_csv(csv_path, fieldnames, rows)

    return noisy


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add progressive English noise to test_chunks.csv B2 -> B3:B21.",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=_DEFAULT_CSV,
        help="Path to test_chunks.csv",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducible noise (default: 42)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print previews without writing the CSV",
    )
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}")
        return 1

    noisy = update_test_chunks_csv(csv_path, seed=args.seed, dry_run=args.dry_run)

    print(f"Source (B{_SOURCE_EXCEL_ROW}): {csv_path}")
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    base = rows[_SOURCE_EXCEL_ROW - 2]["chunk_string"]
    print(f"  {base[:120]}{'...' if len(base) > 120 else ''}\n")

    for i, text in enumerate(noisy, start=_FIRST_NOISY_EXCEL_ROW):
        preview = text[:100] + ("..." if len(text) > 100 else "")
        print(f"B{i} ({len(text)} chars): {preview}")

    if args.dry_run:
        print("\n(dry-run: CSV not modified)")
    else:
        print(f"\nWrote B{_FIRST_NOISY_EXCEL_ROW}–B{_LAST_NOISY_EXCEL_ROW} to {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
