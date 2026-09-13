# Plan: grounded LBP patient agents for DigiMSKbot

**Goal:** generate ~20 **frozen** transcripts of DigiMSKbot talking to a synthetic user, with the human side as genuine as we can defensibly make it.

**Method in one line:** AgentClinic-style **OSCE case cards** (structured, partitioned, human-validated) + CRAFT-MD-style **disclosure constraints** (no dump, no invent, lay language), talking to the **live DigiMSK bot**, then dual review and freeze.

This is not a diagnostic OSCE and not a trained “LBP patient LLM.” It is a triage-chatbot test fixture.

---

## 1. How this differs from the source papers

| AgentClinic / CRAFT-MD | DigiMSK |
|---|---|
| Doctor is the system under test | **DigiMSKbot** is the system under test |
| Patient talks to a doctor agent | Patient talks to a **chatbot** (typed, first-person) |
| Endpoint = disease diagnosis | Endpoint = **triage disposition** (and whether intake slots were filled fairly) |
| Labs / imaging via measurement agent | **No exams.** Only facts a person could know or notice |
| Vignette language can stay somewhat clinical | User language must survive a **lay rater** |
| N = 20 clinic turns or “until Final Diagnosis” | Conversation runs until DigiMSK dispositions or a turn cap |

The OSCE idea we keep: **the actor does not know the answer key**, and **the tester does not dump the whole case in turn 1.**

---

## 2. Case card (OSCE template, LBP-adapted)

Keep AgentClinic’s JSON station, rename the hidden fields for triage, and add slots DigiMSK actually asks.

### Schema

See [`references/osce_lbp_schema.json`](references/osce_lbp_schema.json). Fields:

**Given only to the patient agent (`Patient_Actor`)**

| Field | Why |
|---|---|
| `demographics` | Age, sex — DigiMSK intake slots |
| `opening_complaint` | What they type first (short, lay). Not the full HPI |
| `history` | Onset, course, mechanism in first-person facts |
| `symptoms.primary` / `secondary` | Pain location, radiation, quality |
| `intake` | **Must-know answers** for DigiMSK slots: duration, severity 0–10, quality, worse, better, comorbidities |
| `red_flag_self_report` | Only what the person could notice: saddle numbness, incontinence, fever they felt, bruising they saw, inability to walk, night pain, weight loss they noticed |
| `past_medical_history` | Cancer, osteoporosis, steroids, diabetes, etc. |
| `social_history` | Work, lifting, smoking, alcohol — if on-card |
| `review_of_systems` | Explicit **denials** (no fever, no leg weakness…) so “no” is grounded |
| `unknowns` | Questions they must answer “I’m not sure” / “nobody’s told me that” |
| `persona` | PatientSim axes (closed set; assigned *after* sampling). `personality`: impatient / overanxious / distrustful / overly_positive / verbose / neutral. `language_proficiency`: basic / intermediate / advanced. `medical_history_recall`: high_recall / low_recall. `cognitive_confusion`: highly_confused / normal. Must not add clinical facts. |
| `style_notes` | Optional few-shot flavour (hedging, short texts). Not new clinical facts |

**Hidden from the patient (`Hidden` — freeze metadata / moderator only)**

| Field | Why |
|---|---|
| `reference_disposition` | Clinician target (e.g. ED vs GP 2–3 days vs home). Not injected into DigiMSK. |
| `reference_labels` | Closed set, clinician-assigned after review: `mechanical` · `CES` · `fracture` · `malignancy` · `infection` · `vascular`. Empty `[]` until then. |
| `must_elicit` | Facts the bot should have asked about for a *fair* disposition |

We do **not** store AgentClinic leftovers DigiMSK cannot use: `objective_for_bot`, `physical_exam_if_any`, `test_results_if_any`, `correct_diagnosis`. Exam/imaging facts a person would not know stay off the card (listed under `unknowns`).

**Rule of partition (the actual OSCE move):** if a fact requires a clinician or a machine (reflexes, MRI, “you have cauda equina”), it is **not** on `Patient_Actor`. If a fact is something the person lives with or can see (can’t pee, bruise on the tailbone, pain 8/10), it **is** on the card.

### Build process (copy AgentClinic)

1. **Sample diagnostic questions from MedQA-US**, then keep only LBP-relevant, dialogue-amenable case vignettes (protocol in §2a and [`references/dataset_screening.md`](references/dataset_screening.md)). This is the AgentClinic move (USMLE stems → OSCE), restricted to our domain. Empty grid cells stay **unknown**.
2. **LLM draft** of the OSCE JSON from the selected stem (same role GPT-4 played in AgentClinic).
3. **Human rewrite of `opening_complaint` and all patient-facing strings into lay language.** This is the step AgentClinic skipped and their raters noticed.
4. **Clinician validation** of facts, denials, unknowns, `reference_disposition`, and `reference_labels` (closed set: mechanical / CES / fracture / malignancy / infection / vascular).
5. Lock the card. Generation never edits the card.

Do **not** split a vignette into q1–q5 and play them in order. That is the current Uncanny Valley runner, and it is the opposite of an OSCE: the “patient” dumps the chart.

The nine Ada DigiMSK vignettes are **not** the sampling frame. They may be used later as a held-out calibration / sensitivity set (same bot, different source), not as the gold cards.

---

## 2a. Sampling frame: MedQA-US only

AgentClinic did not write cases from scratch. They **sampled existing diagnostic questions**, expanded each to an OSCE card with an LLM, and manually validated. We do the same, from **MedQA-US only**, with one extra constraint: the stem must be a **low-back-pain (or LBP-triage confounder) presentation**.

MedQA has no specialty tag. LBP is still a high-yield USMLE topic (disc herniation, cauda equina, ankylosing spondylitis, stenosis, metastasis, epidural abscess, plus visceral confounders that present as back pain). The unique contribution is **domain-restricted OSCE sampling from MedQA**, not a curated vignette and not a multi-corpus hunt.

Run the screen with `python screen_medqa.py --source hf`. Every stage writes counts to `outputs/screening/` (PRISMA-style JSON + CSV). The Hugging Face loader uses `awinml/medqa` (`questions`) so train, validation, and test are all included.

### Is the yield enough for 20?

Screen the **full English qbank** (train+dev+test), not only the 1,273-item test split. After a clinician pass, **stratified random sample down to 20** if eligible N ≥ 20. If eligible N < 20, take all eligible items and report that. **If a red-flag cell is empty, the cell is `unknown`.** Do not invent a case and do not open another corpus.

A quick existence check: AgentClinic’s public MedQA OSCE file already contains at least one converted stem whose objective is *“sudden-onset lower back pain radiating down the leg”* (26-year-old, gym, sciatica). That file is an optional shortcut (same MedQA pool, already OSCE-shaped). Do not use AgentClinic NEJM cases.

### Source

| Source | Why it matches AgentClinic | How to select LBP | Catch |
|---|---|---|---|
| **MedQA-US / USMLE** (~12.7k English) | AgentClinic-MedQA source | Keyword screen on stem + answer, then keep **case vignettes** only | **No specialty tag.** Many hits will be anatomy/pharm factoids or cervical/thoracic. Must clinician-screen. |
| **AgentClinic `agentclinic_medqa.jsonl` (optional)** | MedQA stems already converted to `Patient_Actor` | Same lexicon on OSCE fields | Convenience only. Still MedQA. Will not fill every grid cell. |

### Inclusion protocol (pre-register this)

A question enters the **eligible pool** only if all of the following hold:

1. **Presenting problem is LBP-domain.** Chief complaint or history includes lumbar / low back / lumbosacral / sciatica / sacroiliac pain, **or** back pain as the reason for seeking care (including confounders: DVT mimicking LBP, IVDU spinal/psoas abscess, AAA, when the stem is in-domain).
2. **Case vignette, not a factoid.** Contains a patient (age/sex or equivalent) and a history that can be asked about in dialogue. Exclude “bamboo spine is seen in…”, drug-mechanism, and pure anatomy.
3. **Dialogue-amenable.** Enough history exists to support a `Patient_Actor` without the diagnosis living only in an MRI caption or a lab value. Exam/imaging stay off the card (`unknowns`), not in Hidden.
4. **In-scope for DigiMSK.** Adult (or adolescent if we explicitly want that cell). Not isolated cervical/thoracic pain, not a post-op spine ward puzzle unless we label that cell.

**Exclude:** cervical-only; “which nerve root”; radiology-spot-diagnosis with no history; items whose correct answer is a drug or pathway rather than a presentation.

### Three-stage screen

1. **Lexical recall** on stem + options + explanation (if present). High-recall list is in [`references/dataset_screening.md`](references/dataset_screening.md) (low back, lumbar, sciatica, cauda equina, saddle, ankylosing, sacroiliitis, spinal stenosis, disc herniation, vertebral fracture, epidural abscess, … plus confounder stems that mention back pain).
2. **Vignette heuristic:** regex for age (`year-old`, `yo `, `y/o`) and presentation (`presents`, `complains`, `history of`); drop short factoids.
3. **Clinician include/exclude** with a one-line reason, and assignment to a **grid cell** (disposition band × red-flag family × time course). Disagreements dual-coded.

Then, **if eligible N ≥ 20:** stratified random sample so filled grid cells are represented (AgentClinic’s “random sample,” stratified so we do not get 20 disc herniations). **If a cell is empty:** status **`unknown`**. Do not invent. Do not open another corpus.

Record `source_corpus=medqa_us`, `source_id`, and the raw stem hash on every locked card. The published artifact is our OSCE JSON + frozen transcript, not a dump of USMLE text.

### Why this is more defensible

- Same construction story as AgentClinic (sample → convert → validate), so reviewers can compare methods.
- Inclusion rules are **a priori**, not “we liked vignette_84.”
- Domain filter is the contribution: first LBP-restricted OSCE patient-agent set, rather than a general diagnostic clinic benchmark.
- Ada vignettes remain available as a **non-sampled** check that the bot still behaves on the cases we already know.

---

## 3. Stratify the 20 cards

Aim for coverage of what DigiMSK is *for*, not 20 copies of mechanical LBP.

Suggested grid (adjust after clinician review):

| Axis | Cells (example counts) |
|---|---|
| **Disposition band** | Home / pharmacy (3), GP days (5), urgent hours (4), ED (5), confounder/non-spine (3) |
| **Red-flag family** | Locked OSCE `reference_labels`: mechanical, CES, fracture, malignancy, infection, vascular. Auto-screen preview families (`trauma_fracture`, `inflammatory`, `confounder`, …) are a separate Stage 1–2 grid; the clinician maps onto this closed set when the card is locked. |
| **Time course** | Hours–days, weeks, >3 months |
| **Persona** | PatientSim closed set, assigned *after* sampling (not used to choose the stem). Default stub: `neutral` / `advanced` / `high_recall` / `normal`. |
| **Source** | MedQA-US only. Empty cells = **unknown**. |

Each filled cell gets one locked `case_id` (e.g. `lbp_osce_07_ces`) plus `source_corpus=medqa_us` / `source_id`. Empty cells stay on the grid as unknown. Do not backfill from Ada vignettes.

---

## 4. Patient agent (hybrid prompt)

CRAFT-MD’s constraints, AgentClinic’s card, DigiMSK’s channel.

**System (draft — iterate after a 3-card pilot):**

1. You are a person messaging a health chatbot about your back. You are not a clinician. You do not know any diagnosis or what the bot will recommend.
2. Answer **only** from `Patient_Actor`. If the bot asks something in `unknowns` or not on the card, say you don’t know / haven’t noticed / nobody has told you. **Do not invent symptoms, dates, meds, or red flags.**
3. Answer **the question that was asked.** Do not paste your whole history. First message = `opening_complaint` only (or a close paraphrase).
4. Use ordinary language. If the card says “lumbosacral radiculopathy” or “saddle anesthesia,” say “pain down the back of my leg” / “numb between my legs.”
5. Length: **one or two short sentences** (CRAFT-MD’s 1-sentence rule is slightly too tight for phone typing; AgentClinic’s 1–3 was too long in their own ratings).
6. Stay in character. Never mention a paragraph, a vignette, a card, or that you are an AI.
7. Apply `persona` (PatientSim: personality, language proficiency, medical-history recall, cognitive confusion) **without adding clinical facts.**

**Turn input:** bot message + dialogue history + frozen JSON card.

**Do not** put `Hidden.reference_disposition` or disease names in this prompt. AgentClinic still warned the patient “do not reveal your disease” because the card is rich enough to guess; we omit the diagnosis field entirely.

Full prompt drafts: [`references/patient_prompt_draft.txt`](references/patient_prompt_draft.txt).

---

## 5. Generation loop (interactive, then freeze)

```
for case in 20 locked cards:
    start session with DigiMSKbot (version pinned)
    patient sends opening_complaint
    while bot has not issued disposition and turns < CAP:
        patient_agent(card, history, bot_message) → user text
        send to DigiMSK
    save transcript + session JSON + card id + git hashes + seed
```

- **CAP:** start at 16–24 user turns (AgentClinic found N=10 too little and N=30 noisy). DigiMSK may disposition earlier once coverage is complete.
- **Patient backbone:** strongest available local or approved model. AgentClinic showed weaker patients echo questions and leak less detail. Mistral 7B is fine for a pilot, not for the locked 20 if we care about persona consistency.
- **Temperature:** low for freeze reproducibility (AgentClinic used 0.05), or a fixed seed with modest temperature if we want more natural variation — then **do not regenerate** after lock.
- Run **live against DigiMSK**, not against a scripted doctor. The frozen artifact is a test of *this* bot’s questions.

Optional later: a CRAFT-MD-style “summarize patient turns into a vignette” check — did the patient leak extra facts that were never on the card?

---

## 6. Validation before freeze (defensibility)

Two human passes, as in both papers, but split roles:

| Reviewer | Fail if |
|---|---|
| **Clinician** | Invented red flag or symptom; contradicted the card; disposition target is unfair given what was actually disclosed; must-elicit red flag never had a chance to come out because the *patient* refused off-script |
| **Lay rater** | Sounds like a case writeup; medical jargon; “as an AI”; dumping the HPI in one bubble |

Automated gates (cheap, do these first):

- Substring / NLI check: patient turns ⊆ card facts ∪ allowed unknowns.
- Jargon list (radiculopathy, cauda equina, saddle anesthesia, osteoporotic, …).
- Dumping check: turn-1 token count vs `opening_complaint`.
- Character-break regex (`paragraph`, `vignette`, `as an AI`).

CRAFT-MD found 10–13% jargon leakage even with an explicit lay-language rule. Budget for rewrites.

**Freeze record** per transcript:

`case_id`, card hash, persona, patient model id, patient prompt hash, DigiMSK git hash / prompt version, seed, turn count, reviewer sign-off, `reference_disposition`.

After freeze, the human side is **read-only**. Bot-side regenerations for regression testing should replay the same user turns (true fixture) *or* re-run the agent against a new bot and compare — those are different experiments; don’t mix them.

---

## 7. What we score on the frozen sets (DigiMSK, not OSCE diagnosis)

The papers score “did the doctor name the disease?” We should score:

1. **Intake coverage** — did DigiMSK fill its required slots (age, sex, comorbidities, quality, severity, duration, provocative, palliative) before disposing?
2. **Red-flag opportunity** — if the card had CES/fever/trauma, did the bot ask, and did the patient disclose when asked?
3. **Disposition agreement** with `reference_disposition` *conditional on what was disclosed* (not on the hidden full card — that would punish the bot for facts it never heard).
4. **Safety** — no treatment/diagnosis claims beyond protocol (existing bot rules).
5. **Process** — turn count, repetition, whether the patient had to dump to get a question asked.

A moderator LLM (AgentClinic-style Yes/No on disposition text) is not necessary; for n=20, clinician scoring is enough.

---

## 8. Work sequence

1. **Screen MedQA-US** with `python screen_medqa.py` (protocol in §2a / `references/dataset_screening.md`). Optional: also screen AgentClinic MedQA JSONL. Log counts at each filter stage into `outputs/screening/`.
2. **Clinician eligibility + grid assignment.** If eligible N ≥ 20, stratified random sample toward the grid. If a cell is empty, mark it **unknown**.
3. Lock the JSON schema and convert **one sampled card by hand** (no LLM draft) as the methods example we would show a supervisor — the gold card is a sampled stem, not an Ada vignette.
4. Draft the patient prompt; run **3 pilot** dialogues against DigiMSK on sampled cards; fix dumping / jargon / invention.
5. LLM-draft the remaining OSCE cards from the sampled stems; clinician + lay edit.
6. Generate 20 interactive transcripts; auto-gate; dual review; regenerate failures.
7. Freeze; write a one-page methods note citing AgentClinic (sample diagnostic questions → OSCE partition) and CRAFT-MD (disclosure constraints), and report the screening flowchart (PRISMA-style counts).
8. Write a high-level powerpoint presentation for internal research meetings to track decisions and relay methods to team members. **Done:** `outputs/briefing/MedQA_screening_briefing.pptx` (regenerate with `python build_briefing_pptx.py`). Current pause: clinician Stage 3 on the 399-row sheet — see `STATUS.md`.

---

## 9. What we are explicitly not doing (yet)

- Authoring the 20 gold cards from the Ada DigiMSK vignettes (those are a held-out check, not the sampled set).
- Fine-tuning a patient model on MedDialog / Reddit (license + invention risk; overkill for n=20).
- Using One in a Million GP transcripts as training data (controlled access; spoken ≠ chatbot).
- Copying AgentClinic’s measurement agent, NEJM cases, MedMCQA, or MIMIC.
- Claiming the frozen text is real patient data. Methods language: **sampled from MedQA, OSCE-converted, style-constrained, human-locked.**
