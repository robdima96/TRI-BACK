# STATUS — read this first

**Paused here (28 Aug 2026).** Auto-screening is done (lexicon v2: DVT + IVDU/spinal abscess confounders; pancreas/abdominal-radiating **removed**). Clinician coding of the eligible pool is **not** done yet. Do not treat the provisional 20 stub cards as locked gold cases.

## Done

1. **Sampling frame locked:** MedQA-US English qbank only (Jin et al.). Empty stratification cells = **unknown**. No MedMCQA, MIMIC, NEJM, Ada vignettes, or invented cases.
2. **Auto-screen run** `20260828T222620Z` (see `outputs/screening/LATEST.txt`):
   - Loaded **12,723** items (train + validation + test)
   - Unique stems **12,721**
   - Auto-eligible for clinician review: **399**
   - Lexicon term hits of note: `confounder_dvt` = 65, `confounder_abscess` = 6
   - Counts: `outputs/screening/audit_20260828T222620Z.md`
   - Coding sheet (stems): `outputs/screening/clinician_review_20260828T222620Z.csv`
   - Prior lexicon (pancreas / radiating abdomen, eligible 401) archived in `outputs/screening/lexicon_v1_visceral_confounders/`
3. **Patient agent** is wired: AgentClinic `Patient_Actor` + CRAFT-MD disclosure rules. `persona` is a PatientSim closed set (`personality`, `language_proficiency`, `medical_history_recall`, `cognitive_confusion`). Hidden is freeze metadata only (`reference_disposition`, `reference_labels`, `must_elicit`) — no diagnosis, exam, or labs. Default live LLM is the **same Vertex Gemini credentials and model as TRI-BACK’s generator**. Switch models with `--model` or `PATIENT_VERTEX_MODEL`.
4. **Live dialogues** will call TRI-BACK at `http://127.0.0.1:8001` when the bot is running.
5. **PI briefing deck:** `outputs/briefing/MedQA_screening_briefing.pptx`

## Next — how we get a fixed set of case cards

Target: **up to 20** locked OSCE cards (fewer if clinician-eligible N < 20).

| Step | What | When |
|---|---|---|
| **3** | Clinician include/exclude + grid cell on the **399** CSV (`clinician_include` = yes/no). | You will arrange this later |
| **4** | `python apply_clinician.py --review … --prior-audit …` → stratified sample ≤20; empty cells stay **unknown** | After the CSV is coded |
| **5** | Hand-convert **one** sampled stem to a lay OSCE card (methods example) | After sample lock |
| **6** | Three-card **Vertex** pilot against TRI-BACK on port 8001; fix dumping / jargon / invention | Bot running |
| **7** | LLM-draft remaining cards from sampled stems; clinician + lay edit; **lock** | After pilot |
| **8** | Generate frozen transcripts (patient agent ↔ TRI-BACK); auto-gates; freeze | After cards lock |

Until Step 3 is done, `clinician_eligible` stays **pending**. The seed-42 sample of 20 is a placeholder for pipeline testing only.

## Commands when you pick this up

```powershell
cd patient_agent
python apply_clinician.py --review outputs/screening/clinician_review_20260828T222620Z.csv --prior-audit outputs/screening/audit_20260828T222620Z.json
python run_patient.py --card PATH --backend vertex --bot-url http://127.0.0.1:8001
python run_patient.py --card PATH --backend vertex --model gemini-2.0-flash
```
