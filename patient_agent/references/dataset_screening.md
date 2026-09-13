# Dataset screening protocol (LBP-eligible diagnostic questions)

**Corpus: MedQA-US only** (Jin et al., 2020/2021; the same USMLE-style English qbank AgentClinic sampled). Empty grid cells are **unknown** — we do not backfill from other datasets.

Pre-register this before looking at items. Goal: an **eligible pool**, then a **stratified random sample of up to 20**. If a stratum has no eligible stem, leave it unknown and report it.

## Corpora

1. **MedQA-US English qbank** (Jin et al., 2020/2021; official English 4-option splits: train 10,178 + validation 1,272 + test 1,273 = **12,723**)  
   Canonical: https://github.com/jind11/MedQA  
   Hugging Face copy used by the screener: `awinml/medqa` config `questions` (falls back to `GBaker/MedQA-USMLE-4-options`, which is **train+test only** and is not the complete qbank).
2. **Optional shortcut:** AgentClinic `agentclinic_medqa.jsonl` — MedQA stems already converted to OSCE JSON. Still MedQA. Do **not** use AgentClinic NEJM files.

Log a PRISMA-style count at each stage (see `outputs/screening/` after a run):

`loaded N → unique (stem hash) → lexical hits → lumbar-puncture-only drop → vignette heuristic → isolated-radiology drop → auto cervical-only drop → clinician eligible → sampled ≤20`

Drop-reason codes are listed in [`filter_codes.md`](filter_codes.md). Every stage’s `drop_reasons` must sum to `N_in − N_out`.

## Stage 1 — lexical (high recall)

Match case-insensitive on question stem, options, and answer (and, for AgentClinic JSON, `Objective_for_Doctor`, `History`, `Primary_Symptom`, `Correct_Diagnosis`).

**Core LBP / lumbar**

- low back, lower back, lumbar, lumbosacral, lumbago
- sciatica, sciatic, radiculopath
- sacroiliac, sacrum, sacral, coccyx, tailbone
- cauda equina, saddle anesth, saddle numb
- spinal stenosis, neurogenic claudication
- disc herni, herniated disc, herniated disk, HNP, nucleus pulposus
- spondylolisthesis, spondylolysis, spondylosis, ankylosing spondyl
- sacroiliitis, HLA-B27 (only if back/spine also present — Stage 3)
- vertebral fracture, compression fracture, osteoporotic fracture
- epidural abscess, discitis, osteomyelitis (spine/vertebral/lumbar)
- spinal met, vertebral met (only if back pain in stem)

**Confounders (keep if the presentation can mimic LBP / spinal infection)**

- back pain + aortic aneurysm / AAA
- DVT / deep vein (or venous) thrombosis (pelvic/iliac DVT mimicking low back pain)
- IV drug use with spinal/epidural/psoas abscess

**Not used:** pancreas / abdominal pain radiating to the back. Those items enter the pool only if another LBP term also hits.

**Stage 1b — lexical false positives (auto-drop, counted separately)**

- hit is only `lumbar puncture` (procedure) with no other LBP lexicon term

## Stage 2 — vignette heuristic (dialogue-amenable)

Keep if the stem looks like a patient case:

- age pattern: `year-old`, `yo `, `y/o`, `years of age`
- and a presentation cue: `presents`, `presented`, `complain`, `history of`, `comes to`, `brought to`

Drop (counted by reason):

- no age pattern
- no presentation cue
- isolated radiology “identify the sign” without a patient

For AgentClinic JSON, Stage 2 is satisfied if `Patient_Actor.History` is non-empty.

## Stage 2b — auto cervical-only drop

Drop if the stem has cervical/neck pain **and** none of: lumbar, low back, sciatic, lumbosacral, cauda equina, sacroiliac. Counted separately. Clinician may still overrule in Stage 3.

## Stage 3 — clinician include / exclude

Checklist (yes required unless noted):

- [ ] Presenting problem is lumbar/low-back domain **or** back pain as the care-seeking complaint (confounders allowed)
- [ ] Enough history for a `Patient_Actor` without inventing facts
- [ ] Exam/labs/imaging a person would not know stay **off** the card (`unknowns`). Do not store them on Hidden.
- [ ] Adult or labelled adolescent; not cervical-only; not a pure anatomy/pharm item
- [ ] Assign grid cell: disposition band × red-flag family × time course, **or** mark unknown. Auto `auto_red_flag_family` is previewed from the **stem** only (not MCQ options), so a CES distractor does not label a mechanical case. When the OSCE card is locked, `Hidden.reference_labels` must be from the closed set `mechanical` · `CES` · `fracture` · `malignancy` · `infection` · `vascular` (empty until assigned).

Free-text **exclude reason** if no.

Two clinicians (or clinician + trained rater) on a 20-item overlap for agreement; disagreements resolved by discussion.

Until Stage 3 is complete, screening reports `clinician_eligible: pending`.

## Stage 4 — sample ≤20

- If eligible N ≥ 20: **stratified random sample** toward the grid; fill cells that have ≥1 eligible item.
- If a cell has 0 eligible items: status **`unknown`**. Do not invent. Do not open another corpus.
- If eligible N < 20: take **all** eligible items and report N < 20.
- Assign `persona` **after** sampling (orthogonal to the stem). Closed set: `personality` (impatient, overanxious, distrustful, overly_positive, verbose, neutral); `language_proficiency` (basic, intermediate, advanced); `medical_history_recall` (high_recall, low_recall); `cognitive_confusion` (highly_confused, normal).
- Store `source_corpus=medqa_us`, `source_id`, stem hash. Prefer derived OSCE cards over raw USMLE stems in any public artifact.

## Ada DigiMSK vignettes

`Uncanny Valley/LBPvignettes_conv.csv` is **out of the sampling frame**. Optional later: run the same patient agent on those nine as a non-sampled sensitivity check.
