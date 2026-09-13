# -*- coding: utf-8 -*-
"""Generate Report_General.md, Report_Methods.md, Report_Prior_Work.md from Zotero HTML exports."""
from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).parent
KNOWN_FIELDS = {
    "Item Type", "Author", "Abstract", "Date", "Language", "Short Title",
    "Library Catalog", "URL", "Accessed", "Volume", "Publisher", "Pages",
    "Publication", "DOI", "Issue", "Journal Abbr", "ISSN", "Date Added",
    "Modified", "License", "Extra", "Place", "PMID", "PMCID", "Section",
}

DROP_FIELDS = {
    "Item Type", "Library Catalog", "URL", "Accessed", "Extra", "ISSN",
    "Date Added", "Modified", "Abstract",
    "Short Title", "Publisher", "Journal Abbr", "Language",
}

KEEP_ORDER = [
    "Publication", "Volume", "Issue", "Pages",
    "Place", "DOI", "License", "PMID", "PMCID",
    "Section",
]

# (folder name, 0-based entry index) -> first author when missing or incorrect in export
AUTHOR_OVERRIDES: dict[tuple[str, int], str] = {
    ("General", 5): "Yanyan Fu",
}


def split_entries(text: str) -> list[str]:
    parts = re.split(r"\n  \*\n", text)
    return [p.strip() for p in parts if p.strip()]


def parse_entry(raw: str) -> tuple[str, dict[str, str], list[str]]:
    lines = raw.splitlines()
    title_lines: list[str] = []
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^    ([^\t]+)\t(.*)$", line)
        if m:
            key = m.group(1).strip()
            if key in KNOWN_FIELDS or key in ("Notes", "Attachments"):
                break
        if line.strip():
            title_lines.append(line.strip())
        i += 1
    title = " ".join(title_lines)
    title = re.sub(r"^\*\s*", "", title).strip()

    fields: dict[str, str] = {}
    authors: list[str] = []
    current_key: str | None = None
    current_parts: list[str] = []

    def flush():
        nonlocal current_key, current_parts
        if not current_key:
            return
        val = " ".join(current_parts).strip()
        val = re.sub(r"\s+", " ", val)
        if current_key == "Author":
            authors.append(val)
        elif current_key not in fields:
            fields[current_key] = val
        else:
            fields[current_key] = fields[current_key] + " " + val
        current_key, current_parts = None, []

    while i < len(lines):
        line = lines[i]
        if line.strip() in ("Tags:", "Attachments", "Notes:"):
            flush()
            i += 1
            while i < len(lines):
                if re.match(r"^    [^\t]+\t", lines[i]):
                    break
                i += 1
            continue
        m = re.match(r"^    ([^\t]+)\t(.*)$", line)
        if m:
            flush()
            current_key = m.group(1).strip()
            rest = m.group(2)
            current_parts = [rest] if rest.strip() else []
        elif current_key and line.strip():
            if line.strip().startswith("o ") or re.match(r"^      o ", line):
                pass
            else:
                # Continuation lines for wrapped fields (e.g. Short Title, Abstract) use
                # 4+ spaces but no "Field\t" pattern.
                current_parts.append(line.strip())
        i += 1
    flush()

    if authors:
        fields["_first_author"] = authors[0]
    return title, fields, authors


def format_entry_md(
    index: int,
    title: str,
    fields: dict[str, str],
    summary: str,
    tool: str | None,
) -> str:
    lines: list[str] = [f"## {index}. {title}", ""]
    auth = fields.get("_first_author", "").strip()
    if auth:
        lines.append(f"**First Author:** {auth}")
    else:
        lines.append("**First Author:** (not listed in the Zotero export)")
    lines.append("")
    lines.append("**Summary:**")
    lines.append("")
    for para in summary.strip().split("\n\n"):
        lines.append(para.strip())
        lines.append("")
    if tool is not None:
        lines.append(f"**Tool:** {tool}")
        lines.append("")
    date = fields.get("Date", "").strip()
    if date:
        lines.append(f"**Date:** {date}")
    for key in KEEP_ORDER:
        if key in DROP_FIELDS:
            continue
        val = fields.get(key, "").strip()
        if val:
            lines.append(f"**{key}:** {val}")
    # any remaining fields not in KEEP_ORDER (excluding internal)
    done = set(KEEP_ORDER) | DROP_FIELDS | {"_first_author", "Author"}
    done |= {"Date"}
    for key in sorted(fields.keys()):
        if key in done or key.startswith("_") or key in DROP_FIELDS:
            continue
        val = fields[key].strip()
        if val:
            lines.append(f"**{key}:** {val}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    # Summaries: 12th-grade reading level; order matches split_entries order per file.
    summaries_general = [
        """Pooling studies on adults with LBP under three months old, the meta-analysis found screening tools more informative for predicting future disability than future pain (for commonly reported tools, pooled discrimination for disability was in an “acceptable” range, while pooled discrimination for pain was weaker and often closer to non-informative). The Örebro questionnaire appeared among the stronger performers for some outcomes. The authors caution that misclassifying patients’ risk remains possible, so tools should not be treated as perfect predictors.""",
        """Out of thousands of records, 60 studies met the reviewers’ criteria. The included work most often reported AI success at diagnosing or classifying chronic pain, while relatively few studies focused on treatment, rehabilitation, or biological mechanisms of pain. Across papers, support vector machines, logistic regression, and random forests were the most common algorithm families. The take-home is a mismatch: AI publications cluster on diagnosis/classification, not on the kinds of mechanism-focused or treatment research the authors argue is needed next.""",
        """After screening 5,695 records, 34 studies (covering 37,509 patients) made the final map of digital triage tools for muscle and joint problems. Only a minority of tools were MSK-specific; most were generic symptom checkers. Reported sensitivity and specificity were all over the place (roughly 39–91% and 23–80% across tools), and reported accuracy ranged from 33% to 98%. The authors’ bottom line is blunt: few tools target MSK well, and many perform poorly on MSK populations, so digital output should support—but not replace—clinical judgment.""",
        """The scoping review catalogued 223 machine-learning papers on LBP (1988–2023). More than half targeted detecting LBP from data; neural networks showed up in 106 articles. Common model inputs were history, demographics, and labs (about two-thirds of studies), and newer work often added imaging. Yet only eight studies reported external validation, only nine shared code, and the reviewers conclude that most papers fall short of best-practice ML reporting—making most of the literature hard to reproduce or trust for real-world use.""",
        """This systematic review pulled together 25 studies on AI decision-support systems applied to degenerative lumbar spine disorders and related LBP. The included papers span tasks such as defining clinical scores, automated assessment, and predicting who is eligible for certain pathways; the reviewers summarize that many studies report strong model metrics (often high discrimination in their own datasets), while also highlighting heterogeneity in methods and endpoints across the field.""",
        """From more than 5,500 screened records, only ten studies (34 prediction models) met the inclusion criteria for chronic LBP in primary care. Reported model discrimination (AUC) ranged from 0.48 to 0.84, calibration was rarely reported, and risk-of-bias assessment raised serious concerns. The Örebro short questionnaire looked strongest among the candidates, but the reviewers still do not recommend routine clinical adoption of these models until higher-quality development and external validation exist.""",
        """The article does not report new trial results; instead it compares evidence on stepped-care models for osteoarthritis with risk-stratified models for LBP and states that current data do not show one broad model type is clearly more effective than the other. It also flags practical gaps: existing programs often ignore social context, other illnesses, and past treatment, and rarely link clinic care, self-management, and community supports in one system.""",
        """Nineteen trials met inclusion criteria for digital programs targeting musculoskeletal conditions. Nine trials reported statistically significant pain reductions, and ten of sixteen trials that measured function showed significant functional gains (several also reported benefits on other secondary outcomes). Because study designs and outcomes differed so much, the authors could not combine results into one pooled effect.""",
        """The search retrieved over 10,000 records and yielded 35 studies describing 30 prognostic clinical prediction rules for nonsurgical LBP. Most rules were still early “development-only” tools; only three had validation evidence highlighted by the reviewers (including the Cassandra rule and Flynn manipulation rules). Crucially, no study showed that applying a rule in practice improved patient outcomes or saved resources, so the review warns against treating most rules as ready for bedside use.""",
    ]

    summaries_methods = [
        """In test conversations, the patient-education bot scored well for giving correct medical information, clear explanations, and empathy, while the screening bot scored well for communication and exploring emotions. Statistical checks indicated the three-bot evaluator setup could match human reviewers closely enough to use for rapid, low-risk chatbot testing without recruiting real patients.""",
        """Across 25 standardized LBP questions, clinician reviewers found that “dumbed down” prompts often made ChatGPT’s answers less clinically complete, whereas neutral or reference-level prompts preserved accuracy better. Readability scores still landed above typical health-literacy targets, and mistakes were more often missing information than outright false claims. Word count and response length did not reliably signal correctness.""",
        """Ninety-eight Dutch clinicians (mostly GPs and primary-care physiotherapists) completed an online survey after watching a video of the decision-support system. Statistical modeling showed “perceived usefulness” was the strongest driver of intention to use the tool; usefulness was shaped by both expected benefits and worries about risks, while worries about losing autonomy and trust in the system’s competence fed into perceived risk. Open-ended answers echoed the same themes.""",
        """The Zotero library entry does not include an abstract for this cataract paper. The article itself describes a large-language-model agent workflow intended to support shared decisions in cataract care (eye disease), which is outside a LBP setting—check the full text for reported accuracy, usability, or patient outcomes.""",
    ]

    # Tool: use short label "STarT" for all STarT Back / STarT MSK–related items
    tools_prior = [
        "Case-Based Reasoning (CBR) configuration software",
        "STarT",
        "SupportPrim PT",
        "unspecified",
        "unspecified",
        "IMPaCT",
        "STarT",
        "selfBACK",
        "PICKUP",
        "DART",
        "DeSSBack",
        "IMPaCT",
        "unspecified",
        "unspecified",
        "unspecified",
        "SupportPrim PT",
        "STarT",
        "SupportPrim",
    ]

    summaries_prior = [
        """Compared with a standard interpolation setup, the case-based reasoning engine raised successful machine configuration rates from about 31% to about 70% in the authors’ tests. In a longitudinal observational run, patients averaged about 32% improvement on a pain scale, about 7% on the Oswestry disability index, and about 13% on a quality-of-life measure.""",
        """At four months, the stratified-care group improved more on disability scores than usual care (adjusted mean difference about 1.8 points on the Roland-Morris scale), and a smaller but still significant gap remained at twelve months (about 1.1 points), matching small-to-moderate effect sizes. By twelve months the intervention also yielded roughly 0.04 extra quality-adjusted life years per person and lower back-pain-related costs in the analysis shown.""",
        """The SupportPrim PT prototype could retrieve clinically similar prior patients from a Norwegian primary-care physiotherapy case base using weighted prognostic features. Similarity matching is presented as technically feasible for feeding treatment suggestions, though this development paper emphasizes algorithm behavior rather than patient outcome gains.""",
        """Among 247 patients with acute LBP, about 47% still had meaningful pain at three months. The best machine-learning model reached modest discrimination for non-recovery (AUC about 0.66), similar to a traditional logistic model but better than usual-practice benchmarks such as therapists’ expectations and the STarT Back tool in this sample. External validation is still required.""",
        """This duplicate library record points to the same Knoop et al. internal-validation study: identical cohort, same headline performance (AUC near 0.66 for the best ML model) and the same conclusion that models beat usual benchmarks but need testing in new sites.""",
        """After rollout, stratified care produced a statistically significant but small average disability improvement versus usual care (mean Roland-Morris difference about 0.7 points), with a much larger effect in the high-risk subgroup (about 2.3 points). Workers took about half as many sick days (median 4 vs 8), sick notes dropped (9% vs 15%), and the economic analysis suggested cost savings alongside small utility gains.""",
        """At twelve months the classification-based pathway did not beat usual care on the main physical-function outcome (mean difference near zero and not significant). Pain intensity improved sooner in the intervention arm (a significant time-by-group pattern), and the intervention group used less healthcare, imaging, and sick leave over follow-up.""",
        """In 461 adults analyzed, the selfBACK app group scored about 0.8 points lower on the Roland-Morris disability scale at three months than usual care alone (a statistically significant but modest gap). About 52% of app users versus 39% of controls improved by at least four points; the authors flag that the clinical importance of the average difference is uncertain.""",
        """In external validation data the PICKUP model discriminated people who developed chronic pain from those who did not with moderate accuracy (AUC about 0.66 with a 95% confidence interval excluding 0.5). Decision-curve analysis suggested risk-based screening could avoid many unnecessary interventions compared with treating everyone the same, though calibration still drifted for some high-risk groups.""",
        """Seventy-eight patients completed the pilot crossover: raw agreement between DART and physiotherapist triage was weak to moderate, but a service-adjusted analysis raised concordance to about 78% with no harmful triage episodes detected. Mean usability scores were in the “excellent” range, supporting a larger definitive trial.""",
        """Thirty-six primary-care patients (23 intervention, 13 control) completed two-month follow-up. Fidelity was weak on the patient side but strong among physicians. Disability and anxiety favored DeSSBack with medium effect sizes (about 0.72 and 0.48), while pain and depression changes were small. Interviews showed doctors felt the tool standardized care, matched treatment to risk, saved time, and was easy to use, supporting a future full trial with tweaks.""",
        """This publication is the trial protocol only: it states planned recruitment, outcomes, and analysis for IMPaCT Back but does not report patient results inside this item.""",
        """On thousands of referral letters, models for rheumatoid arthritis reached AUC-ROC near 0.78, osteoarthritis near 0.71, fibromyalgia near 0.81, and chronic follow-up near 0.63 when validated across sites. The RA classifier prioritized true RA cases better than the manual triage process; authors argue the pipeline could reduce workload if deployed responsibly.""",
        """Across thirteen outcome endpoints, individual machine-learning models achieved AUC values roughly between 0.49 and 0.65 under cross-validation. Combining all predictions into one patient-level profile still agreed with clinician-judged outcomes for about three-quarters of patients, and chart review of “predicted negative” cases supported the algorithms more often than chance.""",
        """Adding NLP-extracted reasons from referral letters raised triage F1 scores by up to about 20 percentage points for some referral categories in 1,608 patients, yet overall triage accuracy remained modest and the authors still judged the models below the bar for standalone clinical use.""",
        """At twelve weeks, roughly 55% of both arms reported feeling better on the global improvement scale (odds ratio near 1.2, not significant), while the decision-support group actually did worse on one function scale than usual care (odds ratio about 0.4 for reaching a clinically important gain). The trial therefore did not show benefit for the AI-supported pathway on the primary end points.""",
        """This UK cluster trial (24 practices) found no meaningful difference between STarT MSK-supported care and usual care on the primary pain and function outcomes averaged over six months (for example, pain scores around 4.4 vs 4.6). Process measures changed—intervention patients more often received information, physio referrals, and OTC analgesics—but overall pain and function did not improve significantly, matching the trial’s neutral headline conclusion.""",
        """This item is a study protocol: it describes the planned SupportPrim trial in general practice (design, outcomes, stratified pathways) and does not present completed trial results here.""",
    ]

    configs = [
        ("General", "Report_General.md", "Zotero Report General.htm", summaries_general, None),
        ("Methods", "Report_Methods.md", "Zotero Report Methods.htm", summaries_methods, None),
        ("Prior Work", "Report_Prior_Work.md", "Zotero Report Prior Work.htm", summaries_prior, tools_prior),
    ]

    for folder, out_name, src_name, summaries, tools in configs:
        path = BASE / folder / src_name
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = split_entries(text)
        if len(entries) != len(summaries):
            raise SystemExit(
                f"{folder}: entry count {len(entries)} != summaries {len(summaries)}"
            )
        if tools and len(tools) != len(entries):
            raise SystemExit("tools length mismatch")

        parts = [
            f"# {folder}: summarized references",
            "",
            f"Summarized from `{src_name}`. Abstracts were replaced with plain-language summaries that emphasize findings, numbers, and conclusions where available. Fields such as Item Type, Library Catalog, URL, Accessed, Extra, ISSN, Date Added, Modified, and Tags were omitted.",
            "",
        ]
        for i, raw in enumerate(entries):
            title, fields, _ = parse_entry(raw)
            override = AUTHOR_OVERRIDES.get((folder, i))
            if override:
                fields["_first_author"] = override
            summ = summaries[i]
            tool = tools[i] if tools else None
            parts.append(format_entry_md(i + 1, title, fields, summ, tool))

        out_path = BASE / folder / out_name
        out_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        print("Wrote", out_path)


if __name__ == "__main__":
    main()
