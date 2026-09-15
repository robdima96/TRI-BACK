#!/usr/bin/env python3
"""Render the two one-page TRI-BACK briefing PDFs for 2026.7.15.

Uses Project/docs/tri_back_pdf.py (dark charcoal, Merriweather, blue rules).

Run from repo root:
  python "Reports/breakdown 2026.7.15/scripts/render_briefing_pdfs.py"

Requires PDF extras (from bot/): reportlab, pypdf, fonttools
  cd bot && pip install -e ".[pdf]"
"""

from __future__ import annotations

import sys
from pathlib import Path


def _repo_root(start: Path) -> Path:
    """Walk up from this script until TRI-BACK root (``bot/`` present)."""
    for candidate in (start, *start.parents):
        if (candidate / "bot").is_dir() and (
            (candidate / "bot" / "app").is_dir() or (candidate / "bot" / "docs").is_dir()
        ):
            return candidate
    raise RuntimeError(f"Could not find TRI-BACK root above {start}")


def _tri_back_pdf_dir(root: Path) -> Path:
    """Locate ``tri_back_pdf.py`` (Project/docs preferred; bot/docs fallback)."""
    for rel in ("Project/docs", "bot/docs"):
        docs = root / rel
        if (docs / "tri_back_pdf.py").is_file():
            return docs
    raise RuntimeError(
        f"Could not find tri_back_pdf.py under {root}/Project/docs or {root}/bot/docs"
    )


BREAKDOWN = Path(__file__).resolve().parents[1]
ROOT = _repo_root(BREAKDOWN)
PDF_DOCS = _tri_back_pdf_dir(ROOT)
PDF_DIR = BREAKDOWN / "pdf"

sys.path.insert(0, str(PDF_DOCS))

from tri_back_pdf import build_markdown_pdf  # noqa: E402

SOURCES = [
    ("01_executive_brief.md", "01_executive_brief.pdf"),
    ("02_file_inventory.md", "02_file_inventory.pdf"),
]


def main() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    # Remove retired briefing PDFs if they linger from earlier packs.
    for stale in (
        "03_api_and_data_flow.pdf",
        "04_llm_vs_orchestration.pdf",
    ):
        old = PDF_DIR / stale
        if old.exists():
            old.unlink()
    for md_name, pdf_name in SOURCES:
        md_path = BREAKDOWN / md_name
        pdf_path = PDF_DIR / pdf_name
        if not md_path.exists():
            print(f"SKIP missing {md_path}")
            continue
        out = build_markdown_pdf(md_path, pdf_path)
        print(f"OK {pdf_name} -> {out}")


if __name__ == "__main__":
    main()
