# Embedding model comparison (RAG retrieval)

`compare_embedding_models.py` benchmarks local encoders on the same corpus and queries:

| Column | Model | Default path | Role |
|--------|--------|----------------|------|
| (production) | **Clinical_sBERT** | `E:\DigiMSKbot\Clinical_sBERT` | RAG (`DIGIMSK_ENCODER_DIR`) |
| G (`GliNER`) | GliNER-BioMed DeBERTa (legacy mean-pool) | `E:\DigiMSKbot\GliNER-BioMed` | Span NER only in production |
| H (`Bio_ClinicalBERT`) | Bio_ClinicalBERT | `E:\DigiMSKbot\Bio_ClinicalBERT` | Benchmark |
| I (`gatortron-base`) | GatorTron-base | `E:\DigiMSKbot\gatortron-base` | Benchmark |

For each model the script:

1. Creates a **temporary** Chroma DB (`hnsw:space: cosine`).
2. Mean-pools and indexes all **66** `chunk_string` rows from `Knowledge Base/Red Flags/chunks/manual/red_flags_manual.csv`.
3. Embeds each patient query (column **B**, rows 2–11) with the **full query string** (same as `scripts/rag_smoke.py`).
4. Retrieves top-k hits and writes a report with **cosine similarity** (`1 - distance`), **distance**, **norm_score** (`1/(1+distance)`), and chunk text.

## Run

From repo root (`bot`):

```bash
python "Embeddings test/compare_embedding_models.py"
python "Embeddings test/compare_embedding_models.py" --dry-run
python "Embeddings test/compare_embedding_models.py" --models GliNER --top-k 3
```

Output is written to `tests/data/results/NER_checklist_matching_with_vignettes_embeddings_test.csv`.

Requirements: `torch`, `transformers`, `sentence-transformers`, `chromadb`, local model folders on disk.

`encode_rag_smoke_test.py` defaults to **production Clinical_sBERT** (`production` / `clinical_sbert` model key) plus MiniLM control; optional legacy GliNER DeBERTa via `--models gliner`.

### Entity-only retrieval (`compare_embedding_models_entities.py`) — legacy benchmark

**Not** production behavior. Production embeds the full vignette (see `compare_embedding_models.py` / `scripts/encode_rag_smoke.py`).

1. Normalize each vignette (column B) and run `encode_user_message` (regex + GliNER).
2. Embed each **per-entity phrase** (`entity_retrieval_phrases`) with the model under test.
3. Query Chroma per phrase and merge by `chunk_id` (best `norm_score` wins).

Results go to columns **J–L**: `GliNER entities`, `Bio_ClinicalBERT entities`, `gatortron-base entities`.

```bash
python "Embeddings test/compare_embedding_models_entities.py"
python "Embeddings test/compare_embedding_models_entities.py" --models GliNER
```
