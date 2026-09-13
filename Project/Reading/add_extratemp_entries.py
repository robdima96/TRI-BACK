# -*- coding: utf-8 -*-
"""Add entries from Extratemp.txt to Report_Methods.md and Report_General.md.

Reuses split_entries, parse_entry, and format_entry_md from
generate_zotero_reports.py for consistent formatting, then merges
new entries into existing reports, sorts all entries by publication
date (earliest first), and renumbers.
"""
from __future__ import annotations

import calendar
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from generate_zotero_reports import split_entries, parse_entry, format_entry_md

EXTRA_DROP_FIELDS = {"Website Title", "Genre", "Repository", "Archive ID"}

MONTH_MAP = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}

# (target_file, summary) for each of the 11 items in Extratemp.txt (0-indexed)
ITEMS = [
    # 0: Serban et al. → Methods
    (
        "Methods",
        "Wide survey of publicly available datasets suitable for data-driven "
        "dialogue system development. **The authors catalogue corpora across "
        "domains and discuss how different datasets can train diverse dialogue "
        "strategies**, noting that **transfer learning between datasets and "
        "incorporation of external knowledge are promising but underexplored**. "
        "Evaluation metrics tied to learning objectives are also reviewed.",
    ),
    # 1: Chen et al. → General
    (
        "General",
        "Overview of deep-learning advances in dialogue systems, divided into "
        "**task-oriented** and **non-task-oriented** categories. Deep learning "
        "enables systems to learn feature representations and generation "
        "strategies from large data with **minimal hand-crafting**. **While "
        "engineering-heavy approaches still dominate practical deployments, "
        "data-driven methods are increasingly feasible and promising.**",
    ),
    # 2: Adamopoulou & Moussiades → General
    (
        "General",
        "Literature review tracing chatbot evolution from early generative ideas "
        "to present-day systems. **Two core implementation technologies are "
        "analyzed: pattern matching and machine learning.** The authors present a "
        "general architectural design, highlight key pre-design considerations, "
        "survey industrial applications, and identify risks of chatbot use with "
        "suggested mitigations. **The review concludes that chatbots still have "
        "significant room for improvement before becoming truly intelligent.**",
    ),
    # 3: Ding et al. → Methods
    (
        "Methods",
        "Systematic scoping review developing an **evaluation framework for "
        "AI-powered conversational agents** used in health interventions. The "
        "abstract in the export is truncated; based on the title and publication "
        "venue (JAMIA), the work provides a **structured framework to guide "
        "assessment of conversational AI** applied to health contexts.",
    ),
    # 4: Shum et al. → Methods
    (
        "Methods",
        "Traces conversational-system evolution from Eliza (1960s) through "
        "task-completion programs and personal assistants to modern social "
        "chatbots like XiaoIce. **Social chatbots must optimize for both "
        "intellectual quotient (IQ) and emotional quotient (EQ), with "
        "conversation-turns per session (CPS) proposed as the key success "
        "metric.** The authors describe technologies from core chat to visual "
        "awareness to skills, and discuss **dynamic emotion recognition and "
        "interpersonal responses** as enablers of long, engaging conversations.",
    ),
    # 5: Chakraborty et al. → General
    (
        "General",
        "Comprehensive review covering chatbot evolution, architecture, and "
        "medical applications, with a focus on ChatGPT. **The article discusses "
        "ChatGPT's architecture and training, its use in medical diagnosis and "
        "treatment, ethical issues, and comparison with other NLP models.** The "
        "authors conclude that **large language models hold immense promise in "
        "healthcare but require further research**, noting current limitations "
        "of ChatGPT-style tools in medical contexts.",
    ),
    # 6: Bocklisch et al. → Methods
    (
        "Methods",
        "Introduces **Rasa NLU and Rasa Core**, open-source Python libraries "
        "for building conversational software. **The tools aim to make "
        "machine-learning-based dialogue management and language understanding "
        "accessible to non-specialist developers**, with design emphasis on ease "
        "of use and bootstrapping from minimal or no initial training data.",
    ),
    # 7: McTear → Methods
    (
        "Methods",
        "Describes the main components of spoken dialogue systems\u2014**speech "
        "recognition, language understanding, dialogue management, "
        "external-source communication, language generation, and speech "
        "synthesis**\u2014and how they integrate into working systems. The article "
        "reviews methods from well-known systems, explores **different "
        "architectures, specification, design, and evaluation approaches**, "
        "surveys available development toolkits, and outlines future prospects.",
    ),
    # 8: Hua et al. → Methods
    (
        "Methods",
        "Systematic review of 266 records producing the **Health Care AI "
        "Chatbot Evaluation Framework (HAICEF)**: a hierarchical framework with "
        "**3 priority domains** (safety, privacy, and fairness; trustworthiness "
        "and usefulness; design and operational effectiveness), **18 "
        "second-level and 60 third-level constructs** covering **271 evaluation "
        "questions**. Distribution across domains: design/operational "
        "effectiveness 40%, trustworthiness/usefulness 39%, safety/privacy/"
        "fairness 21%. **The framework accommodates both patient-facing and "
        "back-office chatbot use cases**; planned next steps include prospective "
        "validation and Delphi consensus.",
    ),
    # 9: Safi et al. → Methods
    (
        "Methods",
        "Scoping review of **45** studies on medical chatbot development "
        "identifying **four main modules: text understanding, dialogue "
        "management, database layer, and text generation**. The most common "
        "technique for text understanding and dialogue management was **pattern "
        "matching** (n=18 and n=25 respectively), and the most common text "
        "generation approach was **fixed output (n=36)** with very few studies "
        "generating original output. **The review notes a recent shift toward "
        "machine-learning-based approaches** and calls for research linking "
        "clinical outcomes to chatbot development techniques.",
    ),
    # 10: Abd-Alrazaq et al. → Methods
    (
        "Methods",
        "Scoping review of **65** studies identifying **27 technical "
        "(non-clinical) metrics** for health chatbot evaluation, grouped by "
        "what they assess: the chatbot as a whole (e.g., usability, classifier "
        "performance, speed), response generation (e.g., comprehensibility, "
        "realism), response understanding (e.g., word error rate), and "
        "aesthetics. **Survey designs and global usability metrics dominated; "
        "the lack of standardization and scarcity of objective measures make "
        "cross-study comparison difficult.** The authors recommend **more "
        "frequent use of conversation-log-derived metrics** and development of "
        "a standardized framework.",
    ),
]


def parse_date_tuple(date_str: str) -> tuple[int, int, int]:
    """Return (year, month, day) for sorting; handles the date formats
    found in the Zotero exports and existing reports."""
    s = date_str.strip()
    # "September/October 2020"
    m = re.match(r"(\w+)/\w+\s+(\d{4})", s)
    if m:
        return (int(m.group(2)), MONTH_MAP.get(m.group(1).lower(), 1), 1)
    # "2018-01" (year-month only)
    m = re.match(r"^(\d{4})-(\d{2})$", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), 1)
    # "2017-03-21" or "2024/02/16"
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # "May 2025"
    m = re.match(r"^(\w+),?\s+(\d{4})$", s)
    if m:
        return (int(m.group(2)), MONTH_MAP.get(m.group(1).lower(), 1), 1)
    # "March 1, 2002" or "November 21, 2017"
    m = re.match(r"^(\w+)\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        return (int(m.group(3)), MONTH_MAP.get(m.group(1).lower(), 1), int(m.group(2)))
    return (9999, 1, 1)


def extract_md_sections(md_text: str):
    """Split a report markdown file into (header, entry_blocks, synthesis).
    entry_blocks is a list of (date_str, block_text) with placeholder numbering."""
    lines = md_text.split("\n")

    first_entry = None
    for i, line in enumerate(lines):
        if re.match(r"^## \d+\.", line):
            first_entry = i
            break
    if first_entry is None:
        return md_text, [], ""

    header = "\n".join(lines[:first_entry])

    synth_start = None
    for i in range(first_entry, len(lines)):
        if lines[i].strip() == "---":
            synth_start = i
            break

    if synth_start is None:
        body = "\n".join(lines[first_entry:])
        synthesis = ""
    else:
        body = "\n".join(lines[first_entry:synth_start])
        synthesis = "\n".join(lines[synth_start:])

    starts = [m.start() for m in re.finditer(r"^## \d+\.", body, re.MULTILINE)]
    blocks = []
    for j, start in enumerate(starts):
        end = starts[j + 1] if j + 1 < len(starts) else len(body)
        block = body[start:end].rstrip()
        date_m = re.search(r"\*\*Date:\*\*\s*(.+)", block)
        date_str = date_m.group(1).strip() if date_m else ""
        block = re.sub(r"^## \d+\.\s*", "## _. ", block, count=1)
        blocks.append((date_str, block))
    return header, blocks, synthesis


def sort_and_renumber(blocks):
    """Sort (date_str, block) pairs by date and renumber headings."""
    dated = [(parse_date_tuple(d), d, b) for d, b in blocks]
    dated.sort(key=lambda x: x[0])
    result = []
    for i, (_, _, block) in enumerate(dated, 1):
        numbered = re.sub(r"^## _\.\s*", f"## {i}. ", block, count=1)
        result.append(numbered)
    return result


def main() -> None:
    text = (BASE / "Extratemp.txt").read_text(encoding="utf-8", errors="replace")
    entries = split_entries(text)
    if len(entries) != 11:
        raise SystemExit(f"Expected 11 entries in Extratemp.txt, got {len(entries)}")

    new_methods: list[tuple[str, str]] = []
    new_general: list[tuple[str, str]] = []

    for i, raw in enumerate(entries):
        title, fields, _ = parse_entry(raw)
        target, summary = ITEMS[i]
        for key in list(fields):
            if key in EXTRA_DROP_FIELDS:
                del fields[key]
        block = format_entry_md(0, title, fields, summary, None)
        block = re.sub(r"^## 0\.\s*", "## _. ", block, count=1).rstrip()
        date_str = fields.get("Date", "").strip()
        if target == "Methods":
            new_methods.append((date_str, block))
        else:
            new_general.append((date_str, block))

    for label, folder, new_blocks in [
        ("Methods", "Methods", new_methods),
        ("General", "General", new_general),
    ]:
        path = BASE / folder / f"Report_{label}.md"
        header, existing, synthesis = extract_md_sections(
            path.read_text(encoding="utf-8")
        )
        merged = existing + new_blocks
        sorted_blocks = sort_and_renumber(merged)
        out = (
            header.rstrip()
            + "\n\n"
            + "\n\n".join(sorted_blocks)
            + "\n\n"
            + synthesis.lstrip("\n")
        )
        path.write_text(out.rstrip() + "\n", encoding="utf-8")
        print(f"{label}: wrote {len(merged)} entries to {path}")


if __name__ == "__main__":
    main()
