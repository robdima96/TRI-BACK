# DigiMSKbot (Month 1)

This scaffold provides a practical Month 1 baseline:

- FastAPI service with health and chat endpoints
- LangGraph orchestration with **SQLite checkpoints** (`thread_id` = `session_id`) and **first-class `messages` state** (append reducer); JSON under `data/sessions/` written each turn for logging/audit (study ids like `admin_15` → `admin_15.json`; other ids → `sess_<sha256>.json`). Disposition audits append and are never wiped by later question turns.
- RAG, generation, and policy stubs
- Tests for API routes and orchestration flow

## Quick start

1. Install dependencies:
   - `pip install -e .[dev]`
2. Run the API:
   - `uvicorn app.main:app --reload`
   - With the study app (`prototypes/digimsk_study_app`): use **port 8001** so Reflex can use 8000:
     `uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`
3. Run tests:
   - `pytest`

Optional **Cloud Run hosting** (GCS mounts, GraphRAG-only bot): see `app/services/public_host/cloud_run/`.

## Knowledge base → Chroma (two steps)

Review CSVs on disk first; ingest only when ready.

1. **Extract** (PDFs → CSV):  
   `python scripts/extract_chunks.py --kb-dir "Knowledge Base/Red Flags"`  
   → `Knowledge Base/Red Flags/chunks/extracted/red_flags_extracted.csv`

2. **Manual registry** (edit + enrich):  
   `Knowledge Base/Red Flags/chunks/manual/red_flags_manual.csv`  
   `python scripts/enrich_chunk_evidence.py`

3. **Ingest** (CSV → Chroma sub-collection; embeddings use **Clinical_sBERT**):  
   `python scripts/chroma_clear.py --empty`  
   `python scripts/ingest_chunks.py --sub-collection red_flags --registry manual`  
   Failsafe corpus:  
   `python scripts/ingest_chunks.py --sub-collection red_flags --chunks-csv "Knowledge Base/Red Flags/chunks/manual/red_flags_manual_failsafe.csv"`

**Models:** GliNER-BioMed (`DIGIMSK_GLINER_MODEL_DIR`) for span NER; Clinical_sBERT (`DIGIMSK_ENCODER_DIR`) for RAG vectors. See `docs/NER_PIPELINE.md`.

See `Knowledge Base/Red Flags/chunks/README.md`.

## Disposition evidence and reasoning

The chatbot uses the graph pack configured by `DIGIMSK_GRAPH_CSV` (no Neo4j
in the chat path). Disposition has two independent evidence toggles:

1. **RAG (`DIGIMSK_RAG=1`)** — Clinical_sBERT semantic search over Chroma plus checklist lexical matches.
2. **GraphRAG (`DIGIMSK_GRAPH_RAG=1`)** — local CSV paths; may use RAG chunk seeds when both are enabled.

`DIGIMSK_DISPOSITION_MODE=deterministic|agentic` independently selects the
reasoning style. Deterministic mode traverses/ranks before drafting. Agentic
mode receives factor matches and an unranked condition-membership tally, then
retrieves evidence lazily through enabled tools; deterministic traversal runs
only as an explicitly logged fallback.

At least one of `DIGIMSK_RAG` / `DIGIMSK_GRAPH_RAG` must be enabled.
`DIGIMSK_GRAPH_INFERENCE=heuristic` preserves current deterministic ranking;
`bayesian` is currently an interface skeleton and is not yet configured.

**Generator evidence:** RAG and graph paths merge independently into `citations` on disposition turns. Disable either path with `=0`.

**Smoke test:** `python scripts/graphrag_smoke.py "I am 70 with severe pain after a recent fall."`

**Chat response fields** (disposition path): `graph_traversal`, `matched_factors`, `candidate_conditions`, `traversed_chunk_ids`. `citations` merge RAG chunk evidence and graph traversal evidence per enabled paths.

Neo4j tooling under `Graphs/` is unchanged and used only for graph exploration / backup workflows.

## Endpoints

- `GET /health` - service health.
- `POST /api/v1/chat` - run one orchestrated chatbot turn (`configurable.thread_id` is the request `session_id`). Optional env: `DIGIMSK_CHECKPOINT_SQLITE` (default `data/langgraph_checkpoints.sqlite`).


