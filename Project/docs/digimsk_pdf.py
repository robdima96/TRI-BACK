# -*- coding: utf-8 -*-
"""DigiMSKbot PDF layout (ReportLab) — source of truth for reading reports and checklist-style PDFs.

Matches `pdf formatting.txt`: US Letter, 0.85\" margins, #26262B background, Merriweather, accent #4A9EFF.
"""
from __future__ import annotations

import io
import os
import re
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
)
try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore[misc, assignment]

try:
    from fontTools.ttLib import TTFont as FTTFont
except ImportError:  # pragma: no cover
    FTTFont = None  # type: ignore[misc, assignment]

# --- Spec constants ---
PAGE_BG = HexColor("#26262B")
ACCENT = HexColor("#4A9EFF")
TEXT_WHITE = HexColor("#FFFFFF")
MARGIN = 0.85 * inch
HEADER_Y_FROM_TOP = 0.55 * inch
FOOTER_Y_FROM_BOTTOM = 0.55 * inch

FONT_REG = "Merriweather"
FONT_BOLD = "Merriweather-Bold"
FONT_ITALIC = "Merriweather-Italic"
FONT_BOLDITALIC = "Merriweather-BoldItalic"

FONTSOURCE_BASE = (
    "https://unpkg.com/@fontsource/merriweather@5.2.5/files/"
)
WOFF2_FILES = {
    FONT_REG: "merriweather-latin-400-normal.woff2",
    FONT_BOLD: "merriweather-latin-700-normal.woff2",
    FONT_ITALIC: "merriweather-latin-400-italic.woff2",
    FONT_BOLDITALIC: "merriweather-latin-700-italic.woff2",
}
TTF_NAMES = {
    FONT_REG: "Merriweather-Regular.ttf",
    FONT_BOLD: "Merriweather-Bold.ttf",
    FONT_ITALIC: "Merriweather-Italic.ttf",
    FONT_BOLDITALIC: "Merriweather-BoldItalic.ttf",
}


def _ensure_merriweather_fonts(font_dir: Path) -> None:
    font_dir.mkdir(parents=True, exist_ok=True)
    if FTTFont is None:
        raise RuntimeError("fonttools is required to prepare Merriweather TTFs (pip install fonttools brotli).")
    for logical, woff_name in WOFF2_FILES.items():
        ttf_path = font_dir / TTF_NAMES[logical]
        if ttf_path.is_file() and ttf_path.stat().st_size > 1000:
            continue
        url = FONTSOURCE_BASE + woff_name
        buf = io.BytesIO()
        with urllib.request.urlopen(url, timeout=120) as resp:
            buf.write(resp.read())
        buf.seek(0)
        font = FTTFont(buf)
        font.flavor = None
        font.save(str(ttf_path))

    registered = set(pdfmetrics.getRegisteredFontNames())
    for logical, fname in TTF_NAMES.items():
        if logical in registered:
            continue
        path = font_dir / fname
        pdfmetrics.registerFont(TTFont(logical, str(path)))


def _esc_xml(ch: str) -> str:
    return ch.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_inline_to_xml(s: str) -> str:
    """Convert one paragraph line's inline Markdown (**bold**, `code`, <url>) to ReportLab XML."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        if i + 1 < n and s[i : i + 2] == "**":
            j = s.find("**", i + 2)
            if j < 0:
                out.append(_esc_xml(s[i]))
                i += 1
                continue
            out.append("<b>" + _esc_xml(s[i + 2 : j]) + "</b>")
            i = j + 2
            continue
        if s[i] == "`":
            j = s.find("`", i + 1)
            if j < 0:
                out.append(_esc_xml(s[i]))
                i += 1
                continue
            out.append(_esc_xml(s[i + 1 : j]))
            i = j + 1
            continue
        m = re.match(r"<(https?://[^>]+)>", s[i:])
        if m:
            url = m.group(1)
            out.append(f'<a href="{url}" color="#FFFFFF">{_esc_xml(url)}</a>')
            i += m.end()
            continue
        out.append(_esc_xml(s[i]))
        i += 1
    return "".join(out)


def parse_markdown_blocks(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return document title and list of (kind, text) where kind is h2|h3|p."""
    lines = text.splitlines()
    title = ""
    pos = 0
    if lines and lines[0].startswith("# ") and not lines[0].startswith("##"):
        title = lines[0][2:].strip()
        pos = 1

    blocks: list[tuple[str, str]] = []
    while pos < len(lines):
        line = lines[pos]
        if not line.strip():
            pos += 1
            continue
        if line.strip() == "---":
            pos += 1
            continue
        if line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
            pos += 1
            continue
        if line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
            pos += 1
            continue
        start = pos
        while pos < len(lines):
            ln = lines[pos]
            if ln.strip() == "---":
                break
            if ln.startswith("## ") or ln.startswith("### "):
                break
            pos += 1
        chunk = lines[start:pos]
        raw = "\n".join(chunk).strip()
        if raw:
            for para in re.split(r"\n\s*\n", raw):
                p = para.strip()
                if p:
                    blocks.append(("p", p))
    return title, blocks


def _page_size() -> tuple[float, float]:
    return letter


def _make_styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            name="DigiTitle",
            fontName=FONT_REG,
            fontSize=18,
            leading=22,
            textColor=TEXT_WHITE,
            linkColor=TEXT_WHITE,
            alignment=0,
            spaceAfter=0,
        ),
        "h2": ParagraphStyle(
            name="DigiH2",
            fontName=FONT_BOLD,
            fontSize=11,
            leading=14,
            textColor=TEXT_WHITE,
            linkColor=TEXT_WHITE,
            alignment=0,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            name="DigiH3",
            fontName=FONT_BOLD,
            fontSize=10,
            leading=13,
            textColor=TEXT_WHITE,
            linkColor=TEXT_WHITE,
            alignment=0,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            name="DigiBody",
            fontName=FONT_REG,
            fontSize=10,
            leading=13,
            textColor=TEXT_WHITE,
            linkColor=TEXT_WHITE,
            alignment=0,
            spaceAfter=5,
        ),
    }


class DigiMSKDocTemplate(BaseDocTemplate):
    def __init__(
        self,
        filename: str,
        *,
        version_date: str,
        total_pages: int | None,
        font_names: dict[str, str],
        **kw,
    ):
        self._version_date = version_date
        self._total_pages = total_pages
        self._font_names = font_names
        page_width, page_height = _page_size()
        frame = Frame(
            MARGIN,
            MARGIN,
            page_width - 2 * MARGIN,
            page_height - 2 * MARGIN,
            id="normal",
            showBoundary=0,
        )
        pt = PageTemplate(
            id="DigiMSK",
            frames=[frame],
            onPage=self._on_page,
            onPageEnd=self._on_page_end,
        )
        BaseDocTemplate.__init__(
            self,
            filename,
            pagesize=letter,
            pageTemplates=[pt],
            **kw,
        )

    def _on_page(self, canv, doc) -> None:
        page_width, page_height = _page_size()
        canv.saveState()
        canv.setFillColor(PAGE_BG)
        canv.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canv.setFillColor(TEXT_WHITE)
        canv.setFont(self._font_names["footer"], 9)
        header_y = page_height - HEADER_Y_FROM_TOP
        canv.drawString(MARGIN, header_y, "DigiMSK Chatbot - Ardern Lab UBC")
        canv.restoreState()

    def _on_page_end(self, canv, doc) -> None:
        page_width, _page_height = _page_size()
        canv.saveState()
        canv.setFillColor(TEXT_WHITE)
        canv.setFont(self._font_names["footer"], 9)
        left = f"version date: {self._version_date}"
        canv.drawString(MARGIN, FOOTER_Y_FROM_BOTTOM, left)
        tp = self._total_pages
        if tp is None:
            right = f"-- {canv.getPageNumber()} of ? --"
        else:
            right = f"-- {canv.getPageNumber()} of {tp} --"
        canv.drawRightString(page_width - MARGIN, FOOTER_Y_FROM_BOTTOM, right)
        canv.restoreState()


def _build_story(
    title: str,
    blocks: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> list[Flowable]:
    story: list[Flowable] = []
    story.append(Paragraph(md_inline_to_xml(title), styles["title"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=10, hAlign="LEFT"))
    first_section = True
    for kind, text in blocks:
        if kind == "h2":
            if not first_section:
                story.append(Spacer(1, 4))
            first_section = False
            story.append(HRFlowable(width="100%", thickness=1.25, color=ACCENT, spaceBefore=4, spaceAfter=6, hAlign="LEFT"))
            h2_text = text.upper()
            story.append(Paragraph(md_inline_to_xml(h2_text), styles["h2"]))
        elif kind == "h3":
            story.append(Paragraph(md_inline_to_xml(text), styles["h3"]))
        else:
            story.append(Paragraph(md_inline_to_xml(text), styles["body"]))
    return story


def build_markdown_pdf(
    md_path: str | Path,
    pdf_path: str | Path,
    *,
    version_date: str | None = None,
    font_dir: str | Path | None = None,
) -> Path:
    """Render a Markdown file to a DigiMSK-styled PDF. Returns output path."""
    md_path = Path(md_path)
    pdf_path = Path(pdf_path)
    if font_dir is None:
        font_dir = Path(__file__).resolve().parent / "fonts"
    else:
        font_dir = Path(font_dir)

    _ensure_merriweather_fonts(font_dir)
    if version_date is None:
        version_date = date.today().strftime("%Y.%m.%d")

    text = md_path.read_text(encoding="utf-8")
    doc_title, blocks = parse_markdown_blocks(text)
    styles = _make_styles()

    font_names = {"footer": FONT_REG}

    def run_build(path: str | Path, total_pages: int | None) -> None:
        # Fresh story each time: ReportLab consumes flowables during build.
        story = _build_story(doc_title, blocks, styles)
        doc = DigiMSKDocTemplate(
            str(path),
            version_date=version_date,
            total_pages=total_pages,
            font_names=font_names,
        )
        doc.build(story)

    if PdfReader is None:
        run_build(pdf_path, None)
        return pdf_path

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        run_build(tmp_path, None)
        reader = PdfReader(tmp_path)
        total = len(reader.pages)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    run_build(pdf_path, total)
    return pdf_path
