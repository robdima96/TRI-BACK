# TRI-BACK grounded patient agent

> **Start here:** [`STATUS.md`](STATUS.md) — what is done, what is parked (399 clinician rows), and the steps to lock ~20 case cards.

AgentClinic-style **OSCE case cards** sampled from **MedQA-US**, plus CRAFT-MD **disclosure constraints**, talking to TRI-BACK. Empty grid cells are **unknown** (no other corpora).

## Verify here

| What | Where |
|---|---|
| **Status + next steps** | [`STATUS.md`](STATUS.md) |
| **PI / team briefing (PowerPoint)** | [`outputs/briefing/MedQA_screening_briefing.pptx`](outputs/briefing/MedQA_screening_briefing.pptx) |
| Methods plan (MedQA-only) | [`lbp_plan.md`](lbp_plan.md) §2a |
| Pre-registered filter protocol | [`references/dataset_screening.md`](references/dataset_screening.md) |
| Drop-reason vocabulary | [`references/filter_codes.md`](references/filter_codes.md) |
| Screening CLI | [`screen_medqa.py`](screen_medqa.py) |
| Clinician Stage 3→4 CLI | [`apply_clinician.py`](apply_clinician.py) |
| Patient-agent CLI | [`run_patient.py`](run_patient.py) |
| Count audit after a run | [`outputs/screening/LATEST.txt`](outputs/screening/LATEST.txt), [`outputs/screening/RUNS.md`](outputs/screening/RUNS.md), and `audit_*.md` |
| Output file map | [`outputs/README.md`](outputs/README.md) |
| Clinician Stage 3 sheet | `outputs/screening/clinician_review_20260828T222620Z.csv` |
| Unit tests | [`tests/test_screen.py`](tests/test_screen.py) |

## Screen MedQA (counts at every stage)

From this folder:

```powershell
pip install -r requirements.txt
python tests/test_screen.py
python screen_medqa.py --source hf --seed 42 --sample-n 20
```

`--source hf` loads official MedQA-US English splits via `awinml/medqa` (`questions`: train+validation+test, n=12,723). Rebuild the briefing deck with `python build_briefing_pptx.py`.

## Patient agent (Vertex = TRI-BACK generator)

Same GCP project, region, and Application Default Credentials as TRI-BACK’s generator (`bot/.env`: `TRI_BACK_VERTEX_PROJECT_ID`, `TRI_BACK_VERTEX_LOCATION`, `TRI_BACK_GENERATOR_MODEL`). Overlay a different Gemini id with `--model` or `PATIENT_VERTEX_MODEL` (see `.env.example`).

```powershell
python run_patient.py --card PATH --backend echo
python run_patient.py --card PATH --backend vertex --bot-url http://127.0.0.1:8001
python run_patient.py --card PATH --backend vertex --model gemini-2.0-flash
```

Live runs assume TRI-BACK on **port 8001**. The agent is given **only** `Patient_Actor`. `Hidden` (disposition target, labels, must-elicit) is never in the prompt.

## Papers

- Schmidgall et al. *AgentClinic.* npj Digit Med (2026). [doi](https://doi.org/10.1038/s41746-026-02674-7)
- Johri et al. CRAFT-MD. Nat Med 31, 77–86 (2025)
- Kyung et al. *PatientSim.* NeurIPS 2025 (persona axes on the OSCE card)
