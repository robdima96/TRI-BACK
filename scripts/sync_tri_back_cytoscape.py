#!/usr/bin/env python3
"""Copy shared TRI-BACK Cytoscape presentation JS into consumer public dirs."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "shared" / "tri_back_cytoscape" / "tri_back_cytoscape.js"
TARGETS = [
    ROOT / "prototypes" / "tri_back_study_app" / "assets" / "tri_back_cytoscape.js",
    ROOT
    / "prototypes"
    / "tri_back_study_app"
    / ".web"
    / "public"
    / "tri_back_cytoscape.js",
    ROOT / "Graphs" / "app" / "public" / "js" / "tri_back_cytoscape.js",
]


def main() -> int:
    if not SRC.is_file():
        print(f"Missing source: {SRC}", file=sys.stderr)
        return 1
    for dest in TARGETS:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC, dest)
        print(f"Copied -> {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
