# Uncanny Valley — vignette dialogue runner

Runs **12-turn** scripted patient–assistant dialogues against your **local Mistral instruct** model for each scenario in `LBPvignettes_conv.csv`.

## Turn structure (per scenario)

| Turn | Role | Phase |
|------|------|--------|
| 1 | Assistant | Greeting |
| 2 | Patient | q1 |
| 3 | Assistant | Response to q1 |
| 4 | Patient | q2 |
| 5 | Assistant | Response to q2 |
| … | … | … |
| 10 | Patient | q5 |
| 11 | Assistant | Response to q5 |
| 12 | Assistant | Triage disposition |

## Setup

```powershell
cd "Uncanny Valley"
pip install -r requirements.txt
```

Model path default: `E:\DigiMSKbot\Mistral7Binstruct` (must contain `*.safetensors`).

## Run

Default prompt (`system_prompt_1.txt`) and all 9 scenarios:

```powershell
python run_dialogues.py
```

**Different system prompt** (easy A/B testing):

```powershell
python run_dialogues.py --prompt system_prompt_2.txt
```

Single scenario (faster smoke test):

```powershell
python run_dialogues.py --scenario vignette_84
```

Validate inputs without loading the GPU model:

```powershell
python run_dialogues.py --dry-run
```

## Output

Written to `output/`:

- `<scenario>_<prompt_stem>_<timestamp>.txt` — human-readable transcript **written after each scenario completes**
- `dialogues_<prompt_stem>_<timestamp>.json` — full run bundle (written at end)
- `SUMMARY_<prompt_stem>_<timestamp>.txt` — index of files (written at end)

Each JSON includes `ada_disposition_reference` from the CSV (for comparison only; not shown to the model).

## Files

| File | Purpose |
|------|---------|
| `run_dialogues.py` | CLI entry point |
| `dialogue_runner.py` | 12-turn orchestration |
| `llm_local.py` | Local transformers inference |
| `vignettes.py` | CSV loader |
| `LBPvignettes_conv.csv` | 9 scenarios, columns q1–q5 |
| `system_prompt_1.txt` | Default system prompt |

## Options

```
--csv PATH           Vignette CSV
--prompt PATH        System prompt file
--model-dir PATH     Local HF model directory
--output-dir PATH    Output folder (default: output/)
--scenario ID        Run one scenario only (repeatable)
--max-new-tokens N   Per-generation token cap (default 500)
--dry-run            List scenarios, no inference
```
