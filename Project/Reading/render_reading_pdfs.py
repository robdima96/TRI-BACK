# -*- coding: utf-8 -*-
"""Build PDFs for General / Methods / Prior Work reports using docs/tri_back_pdf.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from docs.tri_back_pdf import build_markdown_pdf  # noqa: E402

REPORTS = [
    (ROOT / "Reading" / "General" / "Report_General.md", ROOT / "Reading" / "General" / "Report_General.pdf"),
    (ROOT / "Reading" / "Methods" / "Report_Methods.md", ROOT / "Reading" / "Methods" / "Report_Methods.pdf"),
    (ROOT / "Reading" / "Prior Work" / "Report_Prior_Work.md", ROOT / "Reading" / "Prior Work" / "Report_Prior_Work.pdf"),
]


def main() -> None:
    for md, pdf in REPORTS:
        out = build_markdown_pdf(md, pdf)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
