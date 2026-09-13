# PDF Data Extraction Prompt — Participant Demographics

Use this prompt with Claude (Opus 4.6) when attaching one or more PDF journal articles. Copy everything below the horizontal rule into the message alongside the attached PDFs.

---

## Role and Task

You are an expert systematic-review data extractor with training in epidemiology and biomedical research methods. Your task is to extract participant demographic data of each attached PDF of an original research article and return the results as a single CSV table. In order to economize the context window/tokens, read only the Methods section of each article on the first pass. Accuracy is paramount: every value you report will be used in a published scoping review and must be defensible against the source text.

## What to Extract

For each PDF, extract exactly the following fields. If a field cannot be determined from the article, enter `NR` (not reported). Never guess, impute, or calculate values the authors did not explicitly state.

| Field | Description |
|---|---|
| `citation` | First author surname, publication year (e.g., `Smith, 2023`) |
| `title` | Full article title |
| `total_n` | Total number of unique participants enrolled or included in the analysis. Use the number for the analysed sample if both enrolled and analysed counts are given. If only a subset of participants is relevant (e.g., the study reports on a subsample), use the number actually studied and note this in `notes`. |
| `age_value` | The reported central-tendency value for participant age (numeric only) |
| `age_measure` | Which measure of central tendency is reported: `mean`, `median`, or `NR` |
| `age_dispersion_value` | The reported dispersion value (e.g., SD, IQR bounds), numeric only. For IQR, format as `lower–upper` (e.g., `45–62`). |
| `age_dispersion_measure` | Type of dispersion: `SD`, `IQR`, `range`, `95% CI`, `SE`, or `NR` |
| `age_source` | Where in the article this age information was found (e.g., `Table 1`, `Results, para 2`, `Abstract`) |
| `n_male` | Number of male participants (integer). Use `NR` if not reported. |
| `pct_male` | Percentage of male participants (numeric, no % sign). Use `NR` if not reported. |
| `n_female` | Number of female participants (integer). Use `NR` if not reported. |
| `pct_female` | Percentage of female participants (numeric, no % sign). Use `NR` if not reported. |
| `sex_gender_term` | Exact term the authors used: `sex`, `gender`, `male/female`, `men/women`, `man/woman`, or other verbatim term |
| `sex_gender_other` | If any category beyond male/female is reported (e.g., non-binary, other, prefer not to say), record the label and count here; otherwise `NA` |
| `sex_gender_source` | Where in the article this sex/gender information was found |
| `notes` | Any important caveats — e.g., `N differs between tables`, `age reported per group only; total calculated by authors`, `conference abstract only`. Leave blank if none. |

## Output Format

Return a single CSV block with a header row followed by one data row per article. Use comma delimiters and enclose any field containing commas or line breaks in double quotes. Example:

```
citation,title,total_n,age_value,age_measure,age_dispersion_value,age_dispersion_measure,age_source,n_male,pct_male,n_female,pct_female,sex_gender_term,sex_gender_other,sex_gender_source,notes
"Lee, 2024","AI Chatbot for Knee Pain Triage",312,54.7,mean,12.3,SD,Table 1,141,45.2,171,54.8,sex,NA,Table 1,
```

Do not include any other text, commentary, or explanation outside of the CSV block, except for the verification checklist described below.

## Rules and Edge Cases

1. **Total sample only.** If the study has multiple arms or groups, report the combined total across all groups. Do not report per-group breakdowns. If the authors provide only per-group data and no combined total, sum the group Ns for `total_n` and note `total_n summed from group counts` in `notes`. Do not attempt to calculate a pooled mean age or combined sex counts from per-group data — mark those fields as `NR` and note the reason.

2. **Age reported as a range only (e.g., "18–65 years").** Set `age_value` to `NR`, set `age_measure` to `NR`, record the range in `age_dispersion_value`, set `age_dispersion_measure` to `range`, and add a note.

3. **Multiple age values reported.** If both mean and median are given, prefer the mean. If age is reported separately for subgroups but not for the overall sample, mark `age_value` as `NR` and note `age reported per subgroup only`.

4. **Sex vs. gender.** Record whichever the authors report. If both sex and gender are reported as separate variables, prefer biological sex. Record the exact term used in `sex_gender_term`.

5. **Percentages not stated.** If the authors give counts but not percentages (or vice versa), compute the missing value only when the total N is unambiguous. Round percentages to one decimal place. Add a note: `pct_male/pct_female calculated`.

6. **Non-human or simulated participants.** If the study uses simulated patients, chatbot test conversations, or no human participants, set `total_n` to `0`, mark all demographic fields as `NA`, and note `no human participants` or the appropriate description.

7. **Systematic reviews and meta-analyses.** If a systematic review or meta-analysis is accidentally included, set `total_n` to `NR`, mark demographics as `NR`, and note `SR/MA — extract from primary studies instead`.

## Mandatory Verification Checklist

After producing the CSV, perform the following sanity checks on every row. Report the checklist results in a brief numbered list below the CSV block. Flag any issues found; if all checks pass for all articles, state that explicitly.

1. **N consistency.** Does `n_male` + `n_female` (+ any `sex_gender_other` count) equal `total_n`? Tolerate a discrepancy of ≤2 due to missing-data participants. Flag discrepancies >2 with the exact values.
2. **Percentage consistency.** Does `pct_male` + `pct_female` (+ any other category) fall within 99.0–101.0%? Flag values outside this range.
3. **Age plausibility.** Is `age_value` between 0 and 110? Flag any value outside this range.
4. **Source cited.** Is every non-`NR` data point accompanied by a source location (`age_source`, `sex_gender_source`)? Flag any missing source.
5. **Cross-reference check.** For each article, briefly confirm that the `total_n` reported is consistent between the abstract, methods, results, and tables (where available). If different sections state different Ns, flag the discrepancy and report which value you used and why.
6. **Decimal-point check.** Verify that age values and percentages have not been misread (e.g., a mean age of 5.47 is likely 54.7; a percentage of 452 is likely 45.2). Flag and correct any obvious decimal-placement errors.
7. **Article-type check.** Confirm each article is an original study with human participants. Flag any review, editorial, commentary, protocol, or simulation-only study.

## Additional Instructions

- Read each PDF thoroughly. Rely solely on the Methods section for each article; if the requested information is not found in the Methods, then and only then, check the Abstract section, followed by the Results section and tables (especially Table 1), followed by the last paragraph of the Introduction.
- When tables and body text conflict, prefer the table value and note the discrepancy.
- Preserve the exact numeric precision reported by the authors (e.g., do not round 54.73 to 55).
- Process all attached PDFs and return all rows in a single CSV block. Maintain the same article order as the PDFs were attached.