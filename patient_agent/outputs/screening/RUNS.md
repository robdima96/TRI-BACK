# Screening runs

Primary methods denominator is the official MedQA-US English 4-option qbank (Jin et al.): train 10,178 + validation 1,272 + test 1,273 = **12,723**.

Current lexicon (v2): no `confounder_pancreas` / `confounder_radiating_abdomen`; added `confounder_dvt` and `confounder_abscess`.

| Run | Folder | Source | Auto-eligible | Notes |
|---|---|---|---:|---|
| **Primary** `20260828T222620Z` | this directory (`LATEST.txt`) | `awinml/medqa` questions, all three splits | 399 | Use this for Stage 3. Lexicon v2. Provisional sample n=20 (seed 42) is **pre-clinician**. |
| Lexicon v1 (visceral) | `lexicon_v1_visceral_confounders/` | same HF source | 401 | Pancreas + abdominal-radiating confounders. Methods comparison only. |
| GBaker sensitivity | `gbaker_train_test_only/` | `GBaker/MedQA-USMLE-4-options` train+test only (n=11,451) | 352 | Missing validation split. Not the methods N. |
| AgentClinic shortcut | `agentclinic_shortcut/` | `agentclinic_medqa.jsonl` (107 OSCE cases) | 1 | Convenience check only. |
| Fixture smoke | `_fixture_smoke/` | `tests/fixtures/tiny_medqa.jsonl` (n=4) | 1 | Unit-test corpus. |

Stage 3: fill `clinician_include` on `clinician_review_20260828T222620Z.csv`, then `python apply_clinician.py --review ... --prior-audit audit_20260828T222620Z.json`.
