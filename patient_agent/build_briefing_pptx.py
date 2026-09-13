"""Build the internal MedQA screening briefing for PI / research meetings.

  python build_briefing_pptx.py
  -> outputs/briefing/MedQA_screening_briefing.pptx
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "briefing" / "MedQA_screening_briefing.pptx"
SCREEN = ROOT / "outputs" / "screening"
PROMPT = ROOT / "references" / "patient_prompt_draft.txt"

BG = RGBColor(0x26, 0x26, 0x2B)
ACCENT = RGBColor(0x4A, 0x9E, 0xFF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MUTED = RGBColor(0xC8, 0xCD, 0xD6)
CARD = RGBColor(0x32, 0x32, 0x3A)

W = Inches(13.333)
H = Inches(7.5)


def _audit() -> dict:
    latest = (SCREEN / "LATEST.txt").read_text(encoding="utf-8")
    run_id = next(
        line.split("=", 1)[1].strip()
        for line in latest.splitlines()
        if line.startswith("run_id=")
    )
    return json.loads((SCREEN / f"audit_{run_id}.json").read_text(encoding="utf-8"))


def _stage(audit: dict, name: str) -> dict:
    return next(s for s in audit["stages"] if s["name"] == name)


def _fmt(n: int) -> str:
    return f"{n:,}"


def _system_instruction() -> str:
    raw = PROMPT.read_text(encoding="utf-8")
    body = raw.split("---", 1)[-1]
    if "TURN PROMPT" in body:
        body = body.split("TURN PROMPT")[0]
    return body.strip()


def _set_run_font(run, *, size_pt: float, bold: bool = False, color=WHITE) -> None:
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Calibri"


def _fill(shape, color: RGBColor) -> None:
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _add_bg(slide) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    _fill(shape, BG)
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(0.08))
    _fill(bar, ACCENT)


def _footer(slide, page: int, total: int) -> None:
    box = slide.shapes.add_textbox(Inches(0.5), Inches(7.12), Inches(10.5), Inches(0.28))
    p = box.text_frame.paragraphs[0]
    run = p.add_run()
    run.text = "DigiMSK  ·  Patient agent  ·  MedQA screening  ·  confidential — internal"
    _set_run_font(run, size_pt=11, color=MUTED)
    num = slide.shapes.add_textbox(Inches(11.6), Inches(7.12), Inches(1.2), Inches(0.28))
    np = num.text_frame.paragraphs[0]
    np.alignment = PP_ALIGN.RIGHT
    nrun = np.add_run()
    nrun.text = f"{page} / {total}"
    _set_run_font(nrun, size_pt=11, color=MUTED)


def _title(slide, text: str, top: float = 0.22) -> None:
    box = slide.shapes.add_textbox(Inches(0.5), Inches(top), Inches(12.3), Inches(0.58))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    _set_run_font(run, size_pt=26, bold=True)


def _rule(slide, top: float = 0.82) -> None:
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(top), Inches(2.2), Inches(0.04)
    )
    _fill(shape, ACCENT)


def _bullets(slide, items: list[str], *, left=0.5, top=1.05, width=12.3, height=5.6, size=17) -> None:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = 0
        p.space_after = Pt(8)
        run = p.add_run()
        run.text = "•  " + item
        _set_run_font(run, size_pt=size, color=WHITE)


def _para(slide, text: str, *, left=0.5, top=1.05, width=12.3, height=1.6, size=16) -> None:
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    _set_run_font(run, size_pt=size, color=WHITE)


def _card(slide, left, top, width, height, heading: str, body: str, *, hsize=13, bsize=13) -> None:
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    _fill(shape, CARD)
    tb = slide.shapes.add_textbox(
        Inches(left + 0.16), Inches(top + 0.1), Inches(width - 0.32), Inches(height - 0.18)
    )
    tf = tb.text_frame
    tf.word_wrap = True
    hp = tf.paragraphs[0]
    hr = hp.add_run()
    hr.text = heading
    _set_run_font(hr, size_pt=hsize, bold=True, color=ACCENT)
    bp = tf.add_paragraph()
    bp.space_before = Pt(4)
    br = bp.add_run()
    br.text = body
    _set_run_font(br, size_pt=bsize, color=WHITE)


def _new(prs) -> object:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide)
    return slide


def build() -> Path:
    audit = _audit()
    run_id = audit["run_id"]
    lex = _stage(audit, "lexical")
    vig = _stage(audit, "vignette_heuristic")
    cx = _stage(audit, "auto_cervical_only")
    dedupe = _stage(audit, "stem_hash_dedupe")
    grid = audit["grid"]
    terms = audit.get("lexicon_term_counts") or {}
    n_elig = cx["n_out"]
    prompt = _system_instruction()

    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    slides: list = []

    def add():
        s = _new(prs)
        slides.append(s)
        return s

    # --- 1 title ---
    s = add()
    kicker = s.shapes.add_textbox(Inches(0.55), Inches(1.7), Inches(12), Inches(0.4))
    kr = kicker.text_frame.paragraphs[0].add_run()
    kr.text = "DIGIMSK  ·  RESEARCH METHODS BRIEFING"
    _set_run_font(kr, size_pt=14, bold=True, color=ACCENT)
    t = s.shapes.add_textbox(Inches(0.55), Inches(2.15), Inches(12.2), Inches(1.6))
    t.text_frame.word_wrap = True
    r = t.text_frame.paragraphs[0].add_run()
    r.text = "Screening MedQA for grounded\nlow-back-pain patient agents"
    _set_run_font(r, size_pt=36, bold=True)
    sub = s.shapes.add_textbox(Inches(0.55), Inches(4.15), Inches(12), Inches(1.2))
    sub.text_frame.word_wrap = True
    sr = sub.text_frame.paragraphs[0].add_run()
    sr.text = (
        "What we have completed, the counts we will report, and the clinician "
        "step still required before ~20 locked case cards."
    )
    _set_run_font(sr, size_pt=18, color=MUTED)
    note = s.shapes.add_textbox(Inches(0.55), Inches(5.7), Inches(12), Inches(0.5))
    nr = note.text_frame.paragraphs[0].add_run()
    nr.text = f"Internal  ·  28 August 2026  ·  UBC DigiMSK  ·  screen {run_id}"
    _set_run_font(nr, size_pt=14, color=MUTED)

    # --- 2 goal ---
    s = add()
    _title(s, "The artefact we are building")
    _rule(s)
    _bullets(
        s,
        [
            "About 20 frozen transcripts of DigiMSKbot talking to a realistic human-side user.",
            "The system under test is DigiMSK (text triage), not a diagnostic doctor agent.",
            "The human side is a grounded patient agent, not a fine-tuned “LBP personality.”",
            "Methods claim: sampled from MedQA, OSCE-converted, style-constrained, human-locked.",
        ],
    )

    # --- 3 hybrid ---
    s = add()
    _title(s, "Two papers, one hybrid (not a copy of either clinic)")
    _rule(s)
    _card(
        s, 0.5, 1.05, 6.05, 2.55,
        "From AgentClinic (Schmidgall et al., 2026)",
        "Sample diagnostic questions → expand to an OSCE JSON → human validate. "
        "The patient agent sees only Patient_Actor. Hidden is freeze metadata (disposition, labels, must-elicit) — not a diagnosis or exam bundle.",
    )
    _card(
        s, 6.75, 1.05, 6.05, 2.55,
        "From CRAFT-MD (Johri et al., 2025)",
        "Do not dump the vignette. Do not invent symptoms. Answer only what was asked. "
        "Lay language. Stay in character. These disclosure rules are what we enforce.",
    )
    _card(
        s, 0.5, 3.8, 12.3, 2.7,
        "What is different for DigiMSK",
        "Endpoint is triage disposition, not disease name. No measurement/exam agent. "
        "User language must survive a lay rater. Conversation stops when DigiMSK dispositions "
        "(or a turn cap). Empty grid cells stay unknown — we do not open another corpus. "
        "Confounders we hunt: DVT mimicking LBP, and IV-drug-use spinal/psoas abscess — not pancreatic/abdominal radiating pain.",
    )

    # --- 4 MedQA dataset ---
    s = add()
    _title(s, "The MedQA-US dataset (our sampling frame)")
    _rule(s)
    _para(
        s,
        "MedQA (Jin et al., 2020/21) is a large-scale medical question-answering corpus built from professional "
        "licensing exams. We use only the English USMLE 4-option subset: each item is a question stem, four "
        "answer choices (A–D), and a gold answer — not a specialty-tagged clinic note and not a dialogue. "
        "Canonical release: github.com/jind11/MedQA  ·  copy we load: huggingface.co/datasets/awinml/medqa "
        "(config “questions”).",
        top=1.0,
        height=1.55,
        size=16,
    )
    _card(
        s, 0.5, 2.65, 4.0, 3.85,
        "How the qbank is arranged",
        "Official splits, not ours: train 10,178 / validation 1,272 / test 1,273 = 12,723. "
        "We screen all three as one pool (not the test split alone). Two duplicate stems were dropped (unique N = 12,721). "
        "There is no LBP or “spine” label — items are mixed USMLE topics.",
        hsize=14,
        bsize=14,
    )
    _card(
        s, 4.7, 2.65, 4.0, 3.85,
        "What our filters read",
        "Stage 1 (lexical) searches stem + options + answer, so a DVT distractor can still pull an item in. "
        "Vignette, cervical-only, and red-flag family use the stem only, so an MCQ option of “cauda equina” does not label a mechanical case. "
        "Denied phrases (“denies weight loss”) are stripped before family preview.",
        hsize=14,
        bsize=14,
    )
    _card(
        s, 8.9, 2.65, 3.9, 3.85,
        "What we do not treat as MedQA",
        "Ada DigiMSK vignettes, MedMCQA, MIMIC, AgentClinic-NEJM. AgentClinic-MedQA JSONL is an optional shortcut (still MedQA stems, already OSCE-shaped) — not a second corpus.",
        hsize=14,
        bsize=14,
    )

    # --- 5 combined methods + PRISMA ---
    s = add()
    _title(s, "Filters and PRISMA counts (same stages, side by side)")
    _rule(s)
    lp = lex["drop_reasons"].get("lumbar_puncture_only", 0)
    nohit = lex["drop_reasons"].get("no_lexicon_hit", 0)
    rows = [
        (
            "0  Load + dedupe",
            "Official train+val+test JSON. Dedupe by SHA-256 of the question stem.",
            f"{_fmt(dedupe['n_in'])} → {_fmt(dedupe['n_out'])}",
            f"{dedupe['dropped']} duplicate stems",
        ),
        (
            "1  Lexical (high recall)",
            "LBP / sciatica / red-flag terms + AAA, DVT, IVDU–spinal/psoas abscess. Drop lumbar-puncture-only.",
            f"{_fmt(lex['n_in'])} → {_fmt(lex['n_out'])}",
            f"{_fmt(nohit)} no hit; {lp} puncture-only",
        ),
        (
            "2  Vignette heuristic",
            "Keep if age (year-old / yo / y/o) AND presentation (presents / complains / history of…). Drop isolated radiology spots.",
            f"{_fmt(vig['n_in'])} → {_fmt(vig['n_out'])}",
            ", ".join(f"{k}={v}" for k, v in sorted(vig["drop_reasons"].items())) or "—",
        ),
        (
            "2b Cervical-only",
            "Drop neck/cervical pain with no lumbar-region terms (lumbar, low back, sciatic, cauda, SI).",
            f"{_fmt(cx['n_in'])} → {_fmt(cx['n_out'])}",
            f"{cx['dropped']} cervical-only",
        ),
        (
            "3–4  Clinician, then ≤20",
            "Include/exclude + grid. Then stratified sample. Empty cells = unknown. Not run yet.",
            f"{_fmt(n_elig)} pending",
            "provisional sample n=20 (seed 42) — replace after coding",
        ),
    ]
    y = 1.0
    hdr_l = s.shapes.add_textbox(Inches(0.5), Inches(y), Inches(7.6), Inches(0.28))
    hl = hdr_l.text_frame.paragraphs[0].add_run()
    hl.text = "Sampling / screening rule"
    _set_run_font(hl, size_pt=12, bold=True, color=ACCENT)
    hdr_r = s.shapes.add_textbox(Inches(8.3), Inches(y), Inches(4.5), Inches(0.28))
    hr = hdr_r.text_frame.paragraphs[0].add_run()
    hr.text = "N in → N out"
    _set_run_font(hr, size_pt=12, bold=True, color=ACCENT)
    y = 1.32
    for title, rule, nflow, extra in rows:
        _card(s, 0.5, y, 7.6, 1.05, title, rule, hsize=13, bsize=12)
        _card(s, 8.25, y, 4.55, 1.05, nflow, extra, hsize=16, bsize=12)
        y += 1.12

    # --- 6 grid ---
    s = add()
    _title(s, "Auto grid preview (not clinician-confirmed)")
    _rule(s)
    rows_g = [
        ("Mechanical / non-specific", "mechanical"),
        ("Trauma / fracture", "trauma_fracture"),
        ("Cauda equina (CES)", "ces"),
        ("Infection", "infection"),
        ("Malignancy", "malignancy"),
        ("Inflammatory (SpA)", "inflammatory"),
        ("Confounder (DVT, AAA, IVDU abscess)", "confounder"),
        ("Unlabelled family", "unknown"),
    ]
    hdr = s.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(12.3), Inches(0.32))
    hrun = hdr.text_frame.paragraphs[0].add_run()
    hrun.text = "Red-flag family                                          Auto N        Sampled (provisional)        Status"
    _set_run_font(hrun, size_pt=14, bold=True, color=ACCENT)
    for i, (label, key) in enumerate(rows_g):
        cell = grid[key]
        status = cell["status"]
        if key in {"ces", "infection"} and cell["auto_n"] < 10:
            status = f"{status} — thin; may become unknown"
        line = f"{label:<48} {cell['auto_n']:>5}                {cell['sampled_n']:>2}                      {status}"
        tb = s.shapes.add_textbox(Inches(0.5), Inches(1.4 + i * 0.52), Inches(12.3), Inches(0.48))
        rr = tb.text_frame.paragraphs[0].add_run()
        rr.text = line
        _set_run_font(rr, size_pt=15, color=WHITE)
    foot = s.shapes.add_textbox(Inches(0.5), Inches(5.7), Inches(12.3), Inches(0.9))
    foot.text_frame.word_wrap = True
    fr = foot.text_frame.paragraphs[0].add_run()
    fr.text = (
        f"Lexicon term hits (an item may match several): DVT={terms.get('confounder_dvt', 0)}, "
        f"abscess confounder={terms.get('confounder_abscess', 0)}, AAA={terms.get('confounder_aaa', 0)}, "
        f"back_pain={terms.get('back_pain', 0)}, lumbar={terms.get('lumbar', 0)}. "
        "Family is assigned from the stem after stripping “denies …” clauses."
    )
    _set_run_font(fr, size_pt=14, color=MUTED)

    # --- 7 parked ---
    s = add()
    _title(s, f"Pause point: {n_elig} items await clinician coding")
    _rule(s)
    _bullets(
        s,
        [
            f"Auto-eligible N = {n_elig} is high-recall, not the gold set. Many hits will fail a close clinical read.",
            f"Coding sheet: outputs/screening/clinician_review_{run_id}.csv  (clinician_include = yes/no + grid).",
            "A seed-42 sample of 20 stub cards exists only to test the pipeline. It will be replaced after coding.",
            "This step is parked until clinician time can be arranged. Nothing is locked.",
        ],
    )

    # --- 8 path to cards ---
    s = add()
    _title(s, "Path to a fixed number of case cards")
    _rule(s)
    _bullets(
        s,
        [
            "After coding: apply_clinician.py. If eligible N ≥ 20, stratified sample down to 20. If N < 20, take all. Empty cells stay unknown.",
            "Hand-convert one sampled stem into a lay OSCE card (the methods example — not an Ada vignette).",
            "Three-card pilot: Vertex patient agent ↔ live DigiMSK on port 8001. Fix dumping, jargon, invention.",
            "LLM-draft the remaining cards from sampled stems; clinician + lay edit; then lock the JSON.",
            "Persona (PatientSim: personality, language proficiency, medical-history recall, cognitive confusion) is assigned after sampling — it does not choose the stem.",
        ],
    )

    # --- 9 system instruction ---
    s = add()
    _title(s, "Patient-agent system instruction (verbatim)")
    _rule(s)
    box = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.45), Inches(0.98), Inches(12.4), Inches(5.95))
    _fill(box, CARD)
    tb = s.shapes.add_textbox(Inches(0.62), Inches(1.1), Inches(12.1), Inches(5.7))
    tf = tb.text_frame
    tf.word_wrap = True
    first = True
    for line in prompt.splitlines():
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(2)
        run = p.add_run()
        run.text = line if line.strip() else " "
        _set_run_font(run, size_pt=12, bold=line.startswith("HOW YOU") or line.startswith("PERSONA") or line.startswith("PATIENT_"), color=ACCENT if line.startswith(("HOW YOU", "PERSONA", "PATIENT_")) else WHITE)
    note2 = s.shapes.add_textbox(Inches(0.5), Inches(6.92), Inches(12.3), Inches(0.18))
    # footer will overlap - put a tiny caption inside the card instead. Skip extra.

    # --- 10 OSCE JSON ---
    s = add()
    _title(s, "OSCE case card (JSON): who sees what")
    _rule(s)
    _para(
        s,
        "AgentClinic’s station idea: the actor does not know the answer key. DigiMSK keeps that partition. "
        "Locked cards also store source_corpus=medqa_us, source_id, and a stem hash.",
        top=0.95,
        height=0.7,
        size=15,
    )
    _card(
        s, 0.5, 1.7, 6.05, 4.75,
        "Patient_Actor — the only block in the prompt",
        "demographics · opening_complaint (first chat bubble, not the full HPI) · history · "
        "symptoms.primary / secondary · intake (duration, severity 0–10, quality, provocative, "
        "palliative, comorbidities) · red_flag_self_report (only what the person could notice: "
        "saddle numbness, bladder/bowel, fever, trauma, weight loss, night pain, leg weakness) · "
        "past_medical_history · social_history · review_of_systems (explicit denials) · unknowns "
        "(must answer “I’m not sure”) · persona (PatientSim: personality, language_proficiency, medical_history_recall, cognitive_confusion — must not add clinical facts).",
        hsize=14,
        bsize=14,
    )
    _card(
        s, 6.75, 1.7, 6.05, 4.75,
        "Hidden — freeze / moderator / clinician only",
        "reference_disposition (clinician target) · reference_labels "
        "(closed set: mechanical, CES, fracture, malignancy, infection, vascular) · "
        "must_elicit (facts the bot should have had a chance to ask). "
        "Never sent to the patient LLM. No objective_for_bot, exam, labs, or correct_diagnosis — "
        "DigiMSK has no measurement agent.",
        hsize=14,
        bsize=14,
    )

    # --- 11 dialogues ---
    s = add()
    _title(s, "After cards lock: conversations with DigiMSK")
    _rule(s)
    _bullets(
        s,
        [
            "Patient LLM uses the same Google Vertex project, region, and ADC as DigiMSK’s generator (default gemini-2.5-flash).",
            "Swap the patient model later with --model or PATIENT_VERTEX_MODEL without changing the bot.",
            "DigiMSK is assumed at http://127.0.0.1:8001 when we generate transcripts.",
            "Stop when the bot escalates, coverage is ready, or it leaves question mode — plus a turn cap (~16–24).",
            "Auto-gates (dumping, jargon, character-break) then clinician + lay review. Freeze; do not regenerate the human side.",
        ],
    )

    # --- 12 claims ---
    s = add()
    _title(s, "How we will describe this (and what we will not)")
    _rule(s)
    _card(
        s, 0.5, 1.1, 12.3, 2.4,
        "Say",
        "Sampled from MedQA-US, OSCE-converted, style-constrained, human-locked. "
        "Inclusion rules were written before inspecting items. Counts are reported at every filter. "
        "Empty red-flag cells are unknown.",
        hsize=16,
        bsize=16,
    )
    _card(
        s, 0.5, 3.7, 12.3, 2.7,
        "Do not say",
        "These are real patients. These are Ada vignettes. We fine-tuned on Reddit/MedDialog. "
        "We backfilled missing CES cases from another dataset. DigiMSK “diagnosed” the USMLE answer.",
        hsize=16,
        bsize=16,
    )

    # --- 13 ask ---
    s = add()
    _title(s, "Ask of the team")
    _rule(s)
    _bullets(
        s,
        [
            f"Protect time for clinician include/exclude on the {n_elig}-row sheet (and a small dual-coded overlap if feasible).",
            "Agree that empty grid cells remain unknown rather than inventing or switching corpora.",
            "After sampling, one person hand-locks the first card in lay language as the methods exemplar.",
            "When DigiMSK is up on port 8001, run the three-card Vertex pilot before generating the full set.",
        ],
    )
    close = s.shapes.add_textbox(Inches(0.5), Inches(5.55), Inches(12.3), Inches(0.9))
    close.text_frame.word_wrap = True
    cr = close.text_frame.paragraphs[0].add_run()
    cr.text = (
        f"Pointers: patient_agent/STATUS.md  ·  "
        f"counts: outputs/screening/audit_{run_id}.md  ·  "
        "rebuild this deck: python build_briefing_pptx.py"
    )
    _set_run_font(cr, size_pt=15, color=ACCENT)

    total = len(slides)
    for i, slide in enumerate(slides, start=1):
        _footer(slide, i, total)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
    sys.exit(0)
