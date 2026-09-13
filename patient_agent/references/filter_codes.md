# Filter and drop-reason codes

These codes appear in `outputs/screening/all_rows_*.jsonl` (`drop_reason`) and in audit `stages[].drop_reasons`. They are the methods vocabulary for the PRISMA-style flowchart.

| Code | Stage | Meaning |
|---|---|---|
| *(empty / null)* | any keep | Item still in the pool at `stage_passed` |
| `duplicate_stem_hash` | stem_hash_dedupe | Same SHA-256 of question stem already kept |
| `no_lexicon_hit` | lexical (Stage 1) | No LBP / confounder lexicon term on stem+options+answer (+ OSCE fields if present) |
| `lumbar_puncture_only` | lexical 1b | Hit is only the procedure “lumbar puncture” |
| `no_age_pattern` | vignette (Stage 2) | No `year-old` / `yo` / `y/o` / `years of age` |
| `no_presentation_cue` | vignette (Stage 2) | Age present but no presents/complains/history of/comes to/brought to |
| `isolated_radiology` | vignette (Stage 2) | Radiology-spot wording and not a patient vignette |
| `cervical_only` | Stage 2b | Cervical/neck pain without lumbar-region terms |
| `clinician_exclude` | Stage 3 | Coded `no` on the review CSV |
| `clinician_blank_pending` | Stage 3 | `clinician_include` still empty |

`stage_passed` on each row is the **last stage the item reached** (`raw`, `lexical`, `vignette`, `auto_eligible`).

Grid statuses: `pending_clinician` (auto N>0), `filled` (sampled), `unknown` (N=0).

Lexicon pattern names (term hits, not drop codes) are the keys in `lib/lexicon.py` `LEXICON_PATTERNS`.
