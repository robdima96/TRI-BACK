"""Split clinical vignette paragraphs into five conversational patient turns.

Reads ``query`` (column B) from ``tests/data/fixtures/LBPvignettes_conv.csv`` for
Excel rows 2–10, splits each paragraph into five chatbot-style messages (columns
``q1``–``q5`` / D–H), and writes the CSV in place.

Splitting follows the pattern in row 2 (``vignette_84``):

1. Demographics + chief complaint
2. Mechanism / onset / duration context
3. Course, location, or night-time / associated symptom detail
4. Severity, modifiers, or further associated symptoms
5. Remaining findings (medications, function, etc.)

Only text from column B is used. Curated splits mirror the row-2 example; an
automatic sentence grouper is used only when no curated entry exists.

Run from repo root::

    python scripts/vignette_to_conv.py
    python scripts/vignette_to_conv.py --dry-run
    python scripts/vignette_to_conv.py --first-row 2 --last-row 10
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CSV = _ROOT / "tests" / "data" / "fixtures" / "LBPvignettes_conv.csv"

_QUERY_COL = "query"
_SOURCE_COL = "source"
_TURN_COLS = ("q1", "q2", "q3", "q4", "q5")
_NUM_TURNS = 5

_EXTRA_SENT_PRIORITY = (0, 3, 1, 2, 4)

_CURATED_TURNS: dict[str, tuple[str, str, str, str, str]] = {
    "vignette_84": (
        "I am a 27 year old female. I have pain in the lower back after a bad fall.",
        "It happened when I slipped and fell backwards onto a hard surface yesterday, landing directly on my lower back and tailbone",
        "Since the fall, I've had aching pain across the lower back and around the area just above my buttocks",
        "The pain is constant and 7 out of 10. It gets worse when I sit or try to bend forward.",
        "I have some mild bruising and tenderness at the site of the fall, but can walk and move around.",
    ),
    "vignette_6": (
        "I am a 20 year old avid male sportsman with low back pain and stiffness.",
        "Pain has lasted > 3 months and is worst in the morning.",
        "The pain wakes me in the second half of the night, and I trouble getting comfortable afterwards.",
        "Pain is improved by exercise, and made worse by sitting for long periods. Range of motion is decreased in the lower back.",
        "I regularly take an anti-inflammatory during the day, and I find my stiffness is worse when I miss a dose. Pain is a 10/10 (severe) and fluctuating.",
    ),
    "vignette_43": (
        "I am a 35 year old female with lower back pain after a fall.",
        "I have had pain in my lower back since slipping and falling yesterday.",
        "The pain started right after the fall and has not gone away.",
        "The pain is 8 out of 10 and gets worse when I move or try to bend.",
        "I do not take any regular medications and have not had any problems like this before.",
    ),
    "vignette_34": (
        "I am a 51 year old male alcoholic with type 2 diabetes, abdominal pain, and back pain.",
        "The abdominal pain feels like it is radiating to the back and is severe 8/10. It's a shooting pain that fluctuates but may last for several hours/days.",
        "This is a recurrent issue, I once attended the ED for the pain, though subsequent episodes were less severe and lasted less than 10 days with long symptom-free intervals.",
        "I have had type 2 diabetes and am having issues with my stool, which has changed colour, smell and consistency.",
        "I have experienced episodes of vomiting, and noticed weight loss in the past two months.",
    ),
    "vignette_33": (
        "I am a 45 year old female with type 2 diabetes and lower back and sciatica pain.back and sciatic pain.",
        "My low back pain has been present for the last 6 months (pain is 2/10). Increasing sciatic pain in the last 2 weeks.",
        "I am constantly thirsty, and taking more frequent bathroom visits. I am feeling weak and fatigued, my concentration has been affected, I have decreased appetite and lost weight.",
        "I have bone tenderness in the low back area and a history of frequent upper respiratory tract infections- had pneumonia in the last year.",
        "I have a long history of anemia that did not improve with iron supplements or multivitamins, and a leg fracture after a simple fall 2 months ago.",
    ),
    "vignette_19": (
        "I am a 72 year old man with low back pain for the last 6 months that is consistent and aching in nature.",
        "Pain is severe (8/10)",
        "and is exacerbated by sitting, lifting heavy objects/activity, coughing, and sneezing.",
        "It is not relieved by OTC painkillers but is reduced by lying on my side.",
        "My lower back and muscles are tender near the spine.",
    ),
    "vignette_14": (
        "I am a 40 year old male with lower back pain no relevant medical or family history.",
        "I have had low back pain at the level of the sacrum (just above tailbone) for 2 months.",
        "The pain radiates down the back of my left leg and there is a throbbing, burning pain behind my left knee.",
        "Pain is a 9/10 (severe) and intermittent",
        "and is exacerbated by bending forward and also by elevating left leg when lying on back.",
    ),
    "vignette_11": (
        "I am a 24 year old woman with several months of progressive low back and hip pain, now 10/10 (severe).",
        "I have stiffness + limited range of motion of the lower back",
        "and my pain is most severe early in the morning",
        "and fades as the day progresses.",
        "The pain is somewhat relieved with a warm shower or over-the-counter analgesics (Tylenol, Ibuprofen).",
    ),
    "vignette_0": (
        "I am a 38 year old guy with lower back pain that developed acutely after lifting boxes 2 weeks ago. The pain is aching in nature, located in the left lumbar area, and associated with spasms.",
        "I had similar episodes several years ago which resolved without seeing a doctor.",
        "I have reduced movement when bending forwards and backwards because of the pain.",
        "Over-the-counter ibuprofen has helped with pain relief.",
        "Pain is usually 8/10, and fluctuates throughout the day, but has been felt every day for 2 weeks.",
    ),
}


def _split_sentences(paragraph: str) -> list[str]:
    text = (paragraph or "").strip()
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"I])', text)
    return [p.strip() for p in parts if p.strip()]


def _group_sizes(num_sentences: int, *, num_turns: int = _NUM_TURNS) -> list[int]:
    if num_sentences < num_turns:
        raise ValueError(
            f"Need at least {num_turns} sentences after expansion; got {num_sentences}"
        )
    sizes = [1] * num_turns
    remaining = num_sentences - num_turns
    for i in range(remaining):
        sizes[_EXTRA_SENT_PRIORITY[i % num_turns]] += 1
    return sizes


def _expand_sentences_to_min(sentences: list[str], minimum: int) -> list[str]:
    expanded = list(sentences)
    while len(expanded) < minimum:
        idx = max(range(len(expanded)), key=lambda i: len(expanded[i]))
        sent = expanded[idx]
        split_at = sent.find(" and ")
        if split_at == -1:
            raise ValueError(
                f"Cannot split into {minimum} turns without adding text: {sent!r}"
            )
        left = sent[:split_at].rstrip()
        right = sent[split_at + 1 :]
        expanded = expanded[:idx] + [left, right] + expanded[idx + 1 :]
    return expanded


def _join_turn_parts(parts: list[str]) -> str:
    return " ".join(p.strip() for p in parts if p.strip()).strip()


def _turn2_opener(sentence: str) -> str:
    s = sentence.strip()
    if s.startswith("I slipped"):
        return f"It happened when {s[0].lower()}{s[1:]}"
    return s


def _auto_paragraph_to_five_turns(paragraph: str) -> tuple[str, str, str, str, str]:
    sentences = _split_sentences(paragraph)
    if not sentences:
        return ("", "", "", "", "")

    if len(sentences) < _NUM_TURNS:
        sentences = _expand_sentences_to_min(sentences, _NUM_TURNS)

    sizes = _group_sizes(len(sentences))
    turns: list[str] = []
    pos = 0
    for turn_idx, size in enumerate(sizes):
        chunk = sentences[pos : pos + size]
        pos += size
        text = _join_turn_parts(chunk)
        if turn_idx == 1:
            text = _turn2_opener(text)
        turns.append(text)

    return tuple(turns[:_NUM_TURNS])  # type: ignore[return-value]


def paragraph_to_five_turns(
    paragraph: str,
    *,
    source: str = "",
) -> tuple[str, str, str, str, str]:
    key = (source or "").strip()
    if key in _CURATED_TURNS:
        return _CURATED_TURNS[key]
    return _auto_paragraph_to_five_turns(paragraph)


def _coverage_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _verify_coverage(paragraph: str, turns: tuple[str, ...]) -> None:
    source = _coverage_tokens(paragraph)
    combined_set = set(_coverage_tokens(" ".join(turns)))
    missing = [t for t in source if t not in combined_set]
    if missing:
        raise ValueError(
            f"Turns missing source tokens: {missing[:12]}{'...' if len(missing) > 12 else ''}"
        )


def _excel_row_to_index(excel_row: int) -> int:
    return excel_row - 2


def process_csv(
    *,
    csv_path: Path,
    first_row: int,
    last_row: int,
    dry_run: bool,
) -> int:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"No header in {csv_path}")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    for col in (_QUERY_COL, *_TURN_COLS):
        if col not in fieldnames:
            raise ValueError(f"Missing column {col!r} in {csv_path}")

    first_idx = _excel_row_to_index(first_row)
    last_idx = _excel_row_to_index(last_row)
    if first_idx < 0 or last_idx >= len(rows) or first_idx > last_idx:
        raise ValueError(
            f"Row range {first_row}-{last_row} invalid for {len(rows)} data rows"
        )

    updated = 0
    for i in range(first_idx, last_idx + 1):
        row = rows[i]
        paragraph = (row.get(_QUERY_COL) or "").strip()
        if not paragraph:
            continue
        source = (row.get(_SOURCE_COL) or "").strip()
        turns = paragraph_to_five_turns(paragraph, source=source)
        _verify_coverage(paragraph, turns)
        for col, value in zip(_TURN_COLS, turns):
            row[col] = value
        updated += 1
        label = source or f"row_{i + 2}"
        print(f"Row {i + 2} ({label}):")
        for col, value in zip(_TURN_COLS, turns):
            preview = value if len(value) <= 110 else value[:107] + "..."
            print(f"  {col}: {preview}")

    if dry_run:
        print(f"Dry run: would update {updated} row(s) in {csv_path}")
        return 0

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {updated} row(s) to {csv_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Split vignette paragraphs into five conversational queries.",
    )
    parser.add_argument("--csv", type=Path, default=_DEFAULT_CSV)
    parser.add_argument("--first-row", type=int, default=2)
    parser.add_argument("--last-row", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    csv_path = args.csv.resolve()
    if not csv_path.is_file():
        sys.stderr.write(f"CSV not found: {csv_path}\n")
        return 1

    try:
        return process_csv(
            csv_path=csv_path,
            first_row=args.first_row,
            last_row=args.last_row,
            dry_run=args.dry_run,
        )
    except (ValueError, RuntimeError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
