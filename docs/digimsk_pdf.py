"""
Shared DigiMSK dark-mode PDF renderer (ReportLab): Merriweather, charcoal background,
blue rules, header line, version date + page numbers in footer.

Used by render_month1_pdf.py and render_checklist_pdf.py.
"""

from __future__ import annotations

import re
import urllib.request
from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, Spacer
from reportlab.platypus.doctemplate import BaseDocTemplate, PageTemplate
from reportlab.platypus.frames import Frame

ROOT = Path(__file__).resolve().parent
FONTS_DIR = ROOT / "fonts"

HEADER_TEXT = "DigiMSK Chatbot - Ardern Lab UBC"
PAGE_BACKGROUND = colors.HexColor("#26262B")
ACCENT_RULE = colors.HexColor("#4A9EFF")
RULE_TITLE_PT = 0.5
RULE_SECTION_PT = 1.25
TEXT = colors.white
# U+25AA small black square — visible list marker in Merriweather (round • was &#8226;)
BULLET_SQUARE = "&#9642;"

VF_ROMAN_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/merriweather/"
    "Merriweather%5Bopsz%2Cwdth%2Cwght%5D.ttf"
)
VF_ITALIC_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/merriweather/"
    "Merriweather-Italic%5Bopsz%2Cwdth%2Cwght%5D.ttf"
)


def ensure_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    vf_roman = FONTS_DIR / "Merriweather-VF.ttf"
    vf_italic = FONTS_DIR / "Merriweather-Italic-VF.ttf"
    if not vf_roman.exists():
        urllib.request.urlretrieve(VF_ROMAN_URL, vf_roman)
    if not vf_italic.exists():
        urllib.request.urlretrieve(VF_ITALIC_URL, vf_italic)

    targets = [
        ("Merriweather-w400.ttf", vf_roman, {"wght": 400, "wdth": 100, "opsz": 18}),
        ("Merriweather-w700.ttf", vf_roman, {"wght": 700, "wdth": 100, "opsz": 18}),
        ("Merriweather-Italic-w400.ttf", vf_italic, {"wght": 400, "wdth": 100, "opsz": 18}),
        ("Merriweather-Italic-w700.ttf", vf_italic, {"wght": 700, "wdth": 100, "opsz": 18}),
    ]
    for name, src, loc in targets:
        out = FONTS_DIR / name
        if out.exists():
            continue
        from fontTools.ttLib import TTFont as TT
        from fontTools.varLib.instancer import instantiateVariableFont

        font = TT(str(src))
        instantiateVariableFont(font, loc)
        font.save(str(out))


def register_merriweather() -> None:
    ensure_fonts()
    base = FONTS_DIR
    pdfmetrics.registerFont(TTFont("Merriweather", str(base / "Merriweather-w400.ttf")))
    pdfmetrics.registerFont(TTFont("Merriweather-Bold", str(base / "Merriweather-w700.ttf")))
    pdfmetrics.registerFont(TTFont("Merriweather-Italic", str(base / "Merriweather-Italic-w400.ttf")))
    pdfmetrics.registerFont(TTFont("Merriweather-BoldItalic", str(base / "Merriweather-Italic-w700.ttf")))
    pdfmetrics.registerFontFamily(
        "Merriweather",
        normal="Merriweather",
        bold="Merriweather-Bold",
        italic="Merriweather-Italic",
        boldItalic="Merriweather-BoldItalic",
    )


def draw_page_background(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(PAGE_BACKGROUND)
    w, h = doc.pagesize
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    canvas.restoreState()


def draw_header(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Merriweather", 9)
    canvas.setFillColor(TEXT)
    w, h = doc.pagesize
    margin = 0.85 * inch
    y = h - 0.55 * inch
    canvas.drawString(margin, y, HEADER_TEXT)
    canvas.restoreState()


def on_page_start(canvas, doc) -> None:
    draw_page_background(canvas, doc)
    draw_header(canvas, doc)


def md_inline_to_xml(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"`([^`]+)`", r"<font name='Merriweather'>\1</font>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def parse_md(path: Path) -> tuple[str, list[tuple[str, list[str]]]]:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = "Untitled"
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        lines = lines[1:]
    sections: list[tuple[str, list[str]]] = []
    current_h2: str | None = None
    current_body: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current_h2 is not None:
                sections.append((current_h2, current_body))
            current_h2 = line[3:].strip()
            current_body = []
        elif current_h2 is not None:
            current_body.append(line)
    if current_h2 is not None:
        sections.append((current_h2, current_body))
    return title, sections


def body_lines_to_flowables(lines: list[str], styles: dict) -> list:
    out: list = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("  - ") or (stripped.startswith("- ") and line.startswith("  ")):
            t = stripped.lstrip()
            if t.startswith("- "):
                t = t[2:]
            out.append(Paragraph(f"{BULLET_SQUARE}&nbsp;&nbsp;{md_inline_to_xml(t)}", styles["Bullet2"]))
            i += 1
            continue
        if stripped.startswith("- "):
            out.append(
                Paragraph(
                    f"{BULLET_SQUARE}&nbsp;&nbsp;{md_inline_to_xml(stripped[2:])}",
                    styles["Bullet"],
                )
            )
            i += 1
            continue
        if stripped.endswith(":") and i + 1 < len(lines) and lines[i + 1].strip().startswith("- "):
            out.append(Paragraph(f"<b>{md_inline_to_xml(stripped)}</b>", styles["Body"]))
            i += 1
            while i < len(lines) and lines[i].strip().startswith("- "):
                out.append(
                    Paragraph(
                        f"{BULLET_SQUARE}&nbsp;&nbsp;{md_inline_to_xml(lines[i].strip()[2:])}",
                        styles["Bullet2"],
                    )
                )
                i += 1
            continue
        out.append(Paragraph(md_inline_to_xml(stripped), styles["Body"]))
        i += 1
    return out


def build_styles():
    base = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Merriweather",
            fontSize=18,
            leading=22,
            textColor=TEXT,
            spaceAfter=12,
            alignment=TA_LEFT,
        ),
        "Section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            fontName="Merriweather-Bold",
            fontSize=11,
            leading=14,
            textColor=TEXT,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Merriweather",
            fontSize=10,
            leading=13,
            textColor=TEXT,
            spaceAfter=5,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Merriweather",
            fontSize=10,
            leading=13,
            textColor=TEXT,
            leftIndent=16,
            bulletIndent=6,
            spaceAfter=3,
        ),
        "Bullet2": ParagraphStyle(
            "Bullet2",
            parent=base["Normal"],
            fontName="Merriweather",
            fontSize=10,
            leading=13,
            textColor=TEXT,
            leftIndent=30,
            spaceAfter=2,
        ),
    }


def build_story(title: str, sections: list[tuple[str, list[str]]], styles: dict) -> list:
    story: list = []
    story.append(Paragraph(md_inline_to_xml(title), styles["Title"]))
    story.append(
        HRFlowable(
            width="100%",
            thickness=RULE_TITLE_PT,
            color=ACCENT_RULE,
            spaceAfter=10,
        )
    )

    for idx, (h2, body_lines) in enumerate(sections):
        if idx:
            story.append(Spacer(1, 6))
        story.append(
            HRFlowable(
                width="100%",
                thickness=RULE_SECTION_PT,
                color=ACCENT_RULE,
                spaceBefore=4,
                spaceAfter=6,
            )
        )
        story.append(Paragraph(h2.upper(), styles["Section"]))
        story.extend(body_lines_to_flowables(body_lines, styles))
    return story


def make_doc_template(target, total_pages: int | None) -> BaseDocTemplate:
    w, h = letter
    lm = rm = tm = bm = 0.85 * inch
    frame = Frame(lm, bm, w - lm - rm, h - tm - bm, id="normal")

    def on_page_end(canvas, doc):
        if total_pages is not None:
            footer_canvas(canvas, doc, total_pages)

    page_template = PageTemplate(
        id="normal",
        frames=[frame],
        onPage=on_page_start,
        onPageEnd=on_page_end,
        pagesize=letter,
    )
    return BaseDocTemplate(
        target,
        pagesize=letter,
        leftMargin=lm,
        rightMargin=rm,
        topMargin=tm,
        bottomMargin=bm,
        pageTemplates=[page_template],
    )


def count_pages(story: list) -> int:
    buf = BytesIO()
    doc = make_doc_template(buf, total_pages=None)
    doc.build(story)
    buf.seek(0)
    try:
        from pypdf import PdfReader

        return len(PdfReader(buf).pages)
    except Exception:
        return 1


def footer_canvas(canvas, doc, total_pages: int) -> None:
    canvas.saveState()
    canvas.setFont("Merriweather", 9)
    canvas.setFillColor(TEXT)
    w, _h = doc.pagesize
    y = 0.55 * inch
    margin = 0.85 * inch
    canvas.drawString(margin, y, f"version date: {date.today().strftime('%Y.%m.%d')}")
    canvas.drawRightString(w - margin, y, f"-- {doc.page} of {total_pages} --")
    canvas.restoreState()


def render_md_to_pdf(md_path: Path, pdf_path: Path) -> int:
    register_merriweather()
    title, sections = parse_md(md_path)
    styles = build_styles()
    story = build_story(title, sections, styles)
    total_pages = count_pages(story)
    # Platypus flowables are consumed by build(); rebuild for the final PDF.
    story = build_story(title, sections, styles)
    out = make_doc_template(str(pdf_path), total_pages=total_pages)
    out.build(story)
    return total_pages
