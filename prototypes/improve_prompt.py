#!/usr/bin/env python3
"""
Analyze prototypes/prompt.txt and report alignment gaps.

Usage:
    python improve_prompt.py
    python improve_prompt.py --prompt path/to/prompt.txt
    python improve_prompt.py --check prompt_2.txt

Writes alignment_specifics.txt (gap analysis) when run without --check.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROTOTYPES_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPT = PROTOTYPES_DIR / "prompt.txt"
IMPROVED_PROMPT = PROTOTYPES_DIR / "prompt_2.txt"
ALIGNMENT_DOC = PROTOTYPES_DIR / "alignment_specifics.txt"

# Topics that must appear in a complete build prompt for TRI-BACK study app.
REQUIRED_TOPICS: list[tuple[str, list[str], str]] = [
    (
        "Existing backend integration",
        ["fastapi", "bot/", "/api/v1/chat", "langgraph", "adapter"],
        "Must call existing bot/ FastAPI service; do not rebuild orchestration.",
    ),
    (
        "API contract",
        ["chatrequest", "chatresponse", "session_id", "escalated", "citations"],
        "Must reference bot/app/schemas.py request/response fields.",
    ),
    (
        "Three-arm experimental design",
        ["group", "30", "adapter", "arm", "variant"],
        "Must define 3 groups, routing, and adapter swap pattern.",
    ),
    (
        "One-time use semantics",
        ["used", "first login", "reset", "lock"],
        "Must define exactly when used=1 is set and admin reset behaviour.",
    ),
    (
        "Inline Cytoscape graphs",
        ["cytoscape", "inline", "graph_trace", "factor", "condition", "chunk"],
        "Must require in-chat graph rendering with schema compatibility.",
    ),
    (
        "Admin dashboard",
        ["admin", "dashboard", "reset", "export"],
        "Must specify admin user management and used-flag reset.",
    ),
    (
        "Project structure",
        ["prototypes/", "reflex", "seed", "sqlite", "readme"],
        "Must deliver directory layout, seed script, and setup docs.",
    ),
    (
        "Non-goals",
        ["non-goal", "out of scope", "oauth", "do not"],
        "Must bound scope to prevent over-engineering.",
    ),
    (
        "Acceptance criteria",
        ["acceptance", "definition of done", "criteria", "checklist"],
        "Must include testable completion checklist.",
    ),
    (
        "Clinical safety UI",
        ["escalat", "emergency", "disclaimer", "safety"],
        "Must surface escalation and non-emergency disclaimer.",
    ),
]


def read_prompt(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def normalize(text: str) -> str:
    return text.lower()


def topic_hits(text: str, keywords: list[str]) -> list[str]:
    norm = normalize(text)
    return [kw for kw in keywords if kw.lower() in norm]


def analyze_prompt(text: str) -> list[dict]:
    rows: list[dict] = []
    for name, keywords, note in REQUIRED_TOPICS:
        matched = topic_hits(text, keywords)
        rows.append(
            {
                "topic": name,
                "matched_keywords": matched,
                "coverage": len(matched) / len(keywords) if keywords else 0.0,
                "note": note,
            }
        )
    return rows


def format_report(source: Path, rows: list[dict]) -> str:
    lines = [
        f"Prompt alignment report: {source.name}",
        "=" * 60,
        "",
    ]
    gaps: list[dict] = []
    for row in rows:
        status = "OK" if row["coverage"] >= 0.4 else "GAP"
        if status == "GAP":
            gaps.append(row)
        kw = ", ".join(row["matched_keywords"]) or "(none)"
        lines.append(f"[{status}] {row['topic']}")
        lines.append(f"      keywords found: {kw}")
        lines.append(f"      need: {row['note']}")
        lines.append("")

    lines.append("-" * 60)
    lines.append(f"Topics with gaps: {len(gaps)} / {len(rows)}")
    if gaps:
        lines.append("")
        lines.append("Priority additions for alignment:")
        for i, row in enumerate(gaps, 1):
            lines.append(f"  {i}. {row['topic']}: {row['note']}")
    else:
        lines.append("All topics meet minimum keyword coverage.")
    lines.append("")
    return "\n".join(lines)


def check_improved_prompt(improved_path: Path) -> int:
    text = read_prompt(improved_path)
    rows = analyze_prompt(text)
    report = format_report(improved_path, rows)
    print(report)
    gap_count = sum(1 for r in rows if r["coverage"] < 0.4)
    return 0 if gap_count == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze TRI-BACK build prompt alignment.")
    parser.add_argument(
        "--prompt",
        type=Path,
        default=DEFAULT_PROMPT,
        help="Original prompt to analyze (default: prototypes/prompt.txt)",
    )
    parser.add_argument(
        "--check",
        type=Path,
        default=None,
        help="Check improved prompt (e.g. prompt_2.txt) and print report only",
    )
    parser.add_argument(
        "--write-report",
        type=Path,
        default=None,
        help="Write text report to this path (default: stdout only for --check)",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check_improved_prompt(args.check)

    original = read_prompt(args.prompt)
    rows = analyze_prompt(original)
    report = format_report(args.prompt, rows)
    print(report)

    if args.write_report:
        args.write_report.write_text(report, encoding="utf-8")
        print(f"Wrote report: {args.write_report}")

    if IMPROVED_PROMPT.is_file():
        print("\nImproved prompt available:", IMPROVED_PROMPT.name)
        improved_rows = analyze_prompt(read_prompt(IMPROVED_PROMPT))
        improved_gaps = sum(1 for r in improved_rows if r["coverage"] < 0.4)
        original_gaps = sum(1 for r in rows if r["coverage"] < 0.4)
        print(
            f"Gap count: {args.prompt.name}={original_gaps} -> "
            f"{IMPROVED_PROMPT.name}={improved_gaps}"
        )

    if ALIGNMENT_DOC.is_file():
        print(f"Alignment specifics: {ALIGNMENT_DOC.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
