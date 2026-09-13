# AgentClinic vs CRAFT-MD: patient-agent methods

Both papers convert static exam vignettes into multi-turn doctor–patient dialogue so they can test whether an LLM can **take a history**, not just answer a paragraph. They differ in how they ground the patient, how tightly they constrain disclosure, and what they score.

CRAFT-MD is cited in AgentClinic as prior dialogue-based evaluation that lacks multimodal tools, bias injection, multilingual cases, and specialist splits. That is fair as a *benchmark* comparison. For **building a patient actor**, CRAFT-MD is often the stricter (and more useful) recipe.

## Side-by-side

| | **AgentClinic** (Schmidgall et al., npj Digit Med 2026) | **CRAFT-MD** (Johri et al., Nat Med 2025; medRxiv 2023) |
|---|---|---|
| **Purpose** | Benchmark *doctor* agents in a simulated clinic (dialogue + tests + images + tools + bias) | Benchmark *conversational diagnostic reasoning* vs static MCQ |
| **Domain** | General MedQA, MIMIC-IV, NEJM images, 9 specialties, 7 languages | Skin disease (140 vignettes; later expanded in the journal version) |
| **Agents** | Patient, **doctor (SUT)**, **measurement**, **moderator** | Patient, **doctor-AI (SUT)**, **grader-AI**, plus human experts |
| **Case representation** | Structured **OSCE JSON**; facts split by agent | Unstructured **case-vignette paragraph** pasted into the patient prompt |
| **How cases are built** | Sample QA → GPT-4 fills JSON → **manual validation** | Existing DermNet quizzes + 40 new resident-written vignettes |
| **Patient grounding** | `Patient_Actor` fields only; diagnosis and labs withheld | Whole vignette (history ± exam text); diagnosis withheld by instruction |
| **Patient prompt style** | Role + 1–3 sentences + “do not reveal your disease” + optional bias | Role + **no medical knowledge** + **1 sentence** + **no new symptoms (penalized)** + **answer only what was asked** + **lay language** + **do not break character** |
| **Disclosure control** | Soft: “convey symptoms if asked”; card dumped in full | Hard: do not dump the paragraph; do not invent; simplify jargon |
| **Exam / labs** | Separate **measurement agent** returns tests on request | If PE exists, it is given to the **doctor after** the history (or stripped in a self-diagnosis condition) |
| **Turn control** | Fixed **N = 20** (ablations 10–30); tests count as turns | Until doctor says `Final Diagnosis:` or asks no `?` |
| **Patient backbone** | GPT-4 default; they show GPT-3.5 / Mixtral patients change doctor accuracy | Same family as the doctor under test (GPT-4 or GPT-3.5) |
| **What is scored** | Open-ended **diagnosis** vs ground truth (moderator Yes/No); patient Likert ratings; clinician realism; bias; tool use | Diagnosis vs MCQ / many-choice / **free response**; history completeness; lay-language adherence; grader agreement |
| **Human check of the patient** | 3 MDs, 20 dialogues: patient realism **6.7/10**; too verbose, echoes questions | Dermatology experts, 120 GPT-4/3.5 dialogues: **13.3% / 10%** used technical jargon; character breaks (“the paragraph does not mention…”); sometimes refuses or takes over questioning |
| **Key empirical warning** | Interactive format much harder than MedQA; coverage of facts only ~67% | Conversation **drops** accuracy vs vignette; **multi-turn did not beat single-turn**; summarization helped GPT-3.5 |

## Patient-agent method, in their own words

### AgentClinic

Construction (from the excerpt and Methods):

1. Take a diagnostic question (USMLE, MIMIC-IV, or NEJM).
2. Expand it to an OSCE JSON with GPT-4.
3. Manually validate.
4. Give `Patient_Actor` to the patient LLM; `Objective_for_Doctor` to the doctor; exam/tests to measurement; `Correct_Diagnosis` to the moderator.

Runtime prompt (code + appendix):

- Dialogue only, 1–3 sentences.
- “You must not reveal your disease explicitly but may only convey the symptoms you have … if you are asked.”
- Entire `Patient_Actor` dict is in the system prompt every turn.
- Optional cognitive/implicit **bias** paragraph.

They **do not** say “do not invent symptoms” or “one sentence” or “simplify terminology.” Clinician raters then observed verbosity and parroting.

### CRAFT-MD

Construction:

1. Keep the vignette as a paragraph (age, sex, symptoms, history, sometimes exam).
2. Repeat each case **10 times** to estimate variance.
3. Experts annotate a subset of conversations.

Runtime prompt (Methods):

> You are a patient. You do not have any medical knowledge. Based upon questions asked, you have to describe your symptoms from the following paragraph: `<case_vignette>`. Do not break character and reveal that you are describing symptoms from a paragraph. Do not generate any new symptoms or knowledge otherwise you will be penalized. Do not reveal more knowledge than what the question asks. Keep your answer to only 1 sentence. Simplify terminology used in the given paragraph to layman language.

Doctor prompt: one short question at a time; stop only when 100% confident; must emit `Final Diagnosis:`.

They **do** penalize invention and dumping. Experts still found jargon leakage and “as an AI language model / the paragraph does not mention” breaks. “I don’t have that information” was common for off-card questions — which is the correct grounded behaviour, but sounds robotic if overused.

## What each method gets right for a patient actor

**AgentClinic is stronger on case engineering**

- Explicit information partition (actor vs exam vs answer key).
- Manual validation of a structured card, not a free paragraph.
- Reusable schema; easy to add demographics, ROS, social history.
- Bias knobs if we ever want adversarial frozen sets.
- Published JSONL we can imitate.

**CRAFT-MD is stronger on patient *behaviour***

- Anti-dumping (“only what the question asks”).
- Anti-hallucination (“no new symptoms … you will be penalized”).
- Lay-language rewrite of clinical jargon.
- Stay in character (don’t mention the vignette).
- One-sentence answers — closer to how people type in a chatbot than AgentClinic’s 1–3 sentences (and AgentClinic still scored as too verbose).
- Expert rubric aimed at the patient (jargon rate, character break), not only at the doctor.

**Shared weaknesses (both papers)**

- No training on real patient speech; both are prompted LLMs.
- Vignette language leaks into the actor (clinical phrasing, complete HPI).
- Patient agents sometimes echo questions, refuse, or take over.
- Grounding is only as good as the card/vignette; neither paper lists **explicit unknowns**.
- Simulated Likert “patient satisfaction” is not human perception (AgentClinic says this).
- Both evaluate a **doctor** making a **diagnosis**. Neither is a triage-chatbot user.

## Implications for DigiMSK

We should **steal AgentClinic’s OSCE card** (structured, partitioned, human-validated) and **steal CRAFT-MD’s patient constraints** (no dump, no invent, lay language, stay in character).

We should **not**:

- Give DigiMSKbot a measurement agent or NEJM images (out of scope).
- Score open-ended *diagnosis* as the primary freeze criterion (DigiMSK outputs a **disposition**).
- Paste the full vignette paragraph the way CRAFT-MD does — that invites dumping and jargon. Put facts in JSON fields, then prompt “answer from this card.”
- Use AgentClinic’s loose “1–3 sentences, convey symptoms if asked” as the only rule; their own raters said patients were too verbose.
- Treat either paper’s GPT-4 patient as “genuine human dialogue.” Realism scores were middling; CRAFT-MD still had 10–13% jargon.

A hybrid prompt plus an LBP-specific card (intake slots + red-flag facts + explicit unknowns) is the defensible path. That is specified in [`lbp_plan.md`](lbp_plan.md).
