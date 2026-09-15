# Clinical extraction pipeline

The encoder builds a **clinical checklist** from three layers:

| Layer | Source | Module | Env |
|-------|--------|--------|-----|
| Regex / demographics | `pattern` | `app/services/encoder.py` | — |
| Safety phrases | `safety_phrase` | `app/services/policy.py` | — |
| GliNER spans | `gliner` | `app/services/gliner_ner.py` | `TRI_BACK_GLINER_MODEL_DIR`, `TRI_BACK_LOAD_GLINER`, `TRI_BACK_LOAD_NER` |

**RAG embeddings** (Chroma ingest + retrieval) use a separate model:

| Role | Default path | Env |
|------|--------------|-----|
| Sentence embeddings | `E:\TRI-BACK\Clinical_sBERT` (fallback `E:\DigiMSKbot\…`) | `TRI_BACK_ENCODER_DIR`, `TRI_BACK_RAG_EMBEDDING_BACKEND`, `TRI_BACK_ENCODER_DIM` |
| Span NER | `E:\TRI-BACK\GliNER-BioMed` (fallback `E:\DigiMSKbot\…`) | `TRI_BACK_GLINER_MODEL_DIR` |

Production loads Clinical_sBERT with `sentence_transformers` (`encode()` + optional L2 normalize).
GliNER-BioMed is **not** used for vectors unless you set `TRI_BACK_RAG_EMBEDDING_BACKEND=hf_mean_pool`
and point `TRI_BACK_ENCODER_DIR` at a Hugging Face / GliNER backbone folder.

Legacy `DIGIMSK_*` names still resolve.

After changing the RAG model, empty Chroma and re-ingest:

```bash
python scripts/chroma_clear.py --empty
python scripts/ingest_chunks.py --sub-collection red_flags --chunks-csv "Knowledge Base/Red Flags/chunks/manual/red_flags_manual_failsafe.csv"
```

## Pattern + safety (substring matching)

- **Patterns**: durations, comorbidities, pain severity, demographics, symptom quality, provocative/palliative phrases.
- **Safety**: `RISK_CATALOG` in `app/services/policy.py` — substring match on the normalized message (and checklist text for policy hits).

## GliNER span NER

Span NER uses the GliNER zero-shot model in `TRI_BACK_GLINER_MODEL_DIR` (default: `GliNER-BioMed`). The bundle must include `gliner_config.json`.

Install GliNER: `pip install -e ".[gliner]"`.

- `TRI_BACK_LOAD_NER=1` — enable span NER
- `TRI_BACK_LOAD_GLINER=1` — load the GliNER model (disable for pattern/safety-only runs)
- `TRI_BACK_GLINER_NER_THRESHOLD` — span confidence threshold (default `0.5`)

## RAG retrieval flow

1. `encode_user_message` builds checklist + entities (patterns, safety, GliNER) for intake and logging.
2. The **full normalized user message** is embedded with `compute_query_embedding` (Clinical_sBERT).
3. `retrieve_evidence` queries Chroma once with that vector and returns top-k chunks.

## Smoke test

```bash
python scripts/NER_checklist_smoke.py -m "I fell yesterday and have severe low back pain."
python scripts/NER_checklist_smoke.py --no-ner -m "diabetes for 5 years, pain 8/10"
```
