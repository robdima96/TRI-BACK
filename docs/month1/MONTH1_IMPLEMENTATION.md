# Month 1 Implementation 

## Goal

Build a safe first version of the chatbot backend that we can test easily.
For each message, the service loads any prior session snapshot, normalizes input, runs clinical encoding and **this-turn-only** red-flag detection, then runs a **linear** LangGraph: preprocess → ingest → encode (often skipped when the API prefilled encoder fields) → retrieve evidence → generate draft → policy gate → finalize. Finally it persists an updated checklist and trimmed transcript.

## Lay explanation of each component

- **FastAPI app (`app/main.py`)**: The HTTP front door. Validates `session_id`, loads prior checklist and chat history from disk, normalizes the user message, runs the encoder once (for checklist merge and embeddings), merges checklist items with history, computes **current-message** red-flag hits, builds initial LangGraph state, invokes the graph, appends this turn to the transcript, saves the session, and returns `ChatResponse`.

- **API schemas (`app/schemas.py`)**: Pydantic models for evidence snippets, encoder entities, per-turn checklist lines, full encoder output, and the `ChatRequest` / `ChatResponse` contract.

- **Settings (`app/config.py`)**: Central configuration: app name/version/environment, encoder and generator model directories, Chroma paths and collection name, embedding dimension and RAG top‑k, optional NER, flags for loading RAG (`DIGIMSK_LOAD_RAG`) and NER (`DIGIMSK_LOAD_NER`), and session storage directory. Loads optional `.env` via `python-dotenv`.

- **Session store (`app/session_store.py`)**: Persists each session as one JSON file under `data/sessions` (filename from SHA-256 of `session_id`). Stores merged `clinical_checklist` and a capped transcript (last 40 messages). Used for multi-turn context and checklist continuity.

- **Orchestrator state (`app/orchestrator/state.py`)**: TypedDict `ChatState` for one graph run: session id, raw and normalized message, checklist and red-flag ids, encoder outputs, evidence, draft/final text, escalation metadata, optional `prefilled_encode` and `conversation_history`.

- **Orchestrator nodes (`app/orchestrator/nodes.py`)**: Python functions that read/update `ChatState` for each step (normalize, pass-through ingest, conditional encode, RAG, generation, policy, finalize).

- **Orchestrator graph (`app/orchestrator/graph.py`)**: Builds a compiled Lang **`StateGraph`** with a fixed edge list from `START` through seven nodes to `END`.

- **Preprocess (`app/services/preprocess.py`)**: Shared normalization: Unicode NFKC, strip invisible characters, collapse whitespace, English case-folding—so encoder, RAG, and generator see one consistent string shape.

- **Encoder / clinical extraction (`app/services/encoder.py`)**: Builds a **clinical checklist** from pattern rules (durations, comorbidities), **safety phrase** matches against `RISK_CATALOG`, and optional Hugging Face NER (`dslim/bert-base-NER` when `DIGIMSK_LOAD_NER` is on). When RAG is enabled, pulls a pooled query vector via `compute_query_embedding` for Chroma; when RAG is off, skips embeddings and returns checklist-focused output.

- **RAG retrieval (`app/services/rag/__init__.py`)**: `retrieve_evidence` queries Chroma with the query embedding when dimension matches settings; if RAG is disabled (`DIGIMSK_LOAD_RAG=0`), returns no evidence; if the vector is missing or wrong length, returns no evidence. `ingest_evidence_chunk` upserts chunks for production-style ingestion.

- **Chroma store (`app/services/rag/store.py`)**: Persistent Chroma client, evidence collection, and **dev seed** of default MSK guideline chunks (with synthetic unit vectors) when the collection is empty.

- **Query embeddings (`app/services/rag/embeddings.py`)**: Loads a local sentence encoder from `encoder_model_dir`, mean-pools hidden states, and returns vectors for retrieval (same dimension as ingested chunks).

- **Generator (`app/services/generator.py`)**: Drafts a reply using a local causal LM (Mistral-style weights under `generator_model_dir`) when `safetensors` are present; otherwise returns a conservative stub string. Accepts prior `conversation_history` and formats evidence into the prompt.

- **Policy (`app/services/policy.py`)**: Named **risk catalog** and `hits_for_clinical_path` (checklist + message). `apply_policy` replaces the draft with an **urgent-care escalation** message when any red-flag id is present.

- **Tests (`tests/`)**: Pytest coverage for health, chat, graph, preprocessing, RAG toggle, session persistence, and escalation across turns.

- **Packaging (`pyproject.toml`)**: Declares dependencies (FastAPI, LangGraph, transformers, torch, Chroma, etc.) and dev tools.

- **Documentation & cluster helpers (repo root / `docs/` / `scripts/`)**: `README.md` quick start; `docs/sockeye/` for UBC ARC notes; `docs/month1/build_pptx*.py` for slide generation; `scripts/sockeye/*.slurm` for Slurm job templates—not loaded at API runtime.

## Exact files

**Application**

- `app/__init__.py`
- `app/main.py`
- `app/schemas.py`
- `app/config.py`
- `app/session_store.py`
- `app/orchestrator/state.py`
- `app/orchestrator/nodes.py`
- `app/orchestrator/graph.py`
- `app/services/preprocess.py`
- `app/services/encoder.py`
- `app/services/generator.py`
- `app/services/policy.py`
- `app/services/rag/__init__.py`
- `app/services/rag/store.py`
- `app/services/rag/embeddings.py`

**Tests**

- `tests/conftest.py`
- `tests/test_health.py`
- `tests/test_chat_route.py`
- `tests/test_graph.py`
- `tests/test_preprocess.py`
- `tests/test_rag_toggle.py`
- `tests/test_session_chat.py`
- `tests/test_escalation_session.py`

**Project / ops / docs (supporting)**

- `pyproject.toml`
- `README.md`
- `docs/month1/MONTH1_IMPLEMENTATION_PLAN.md` (original plan)
- `docs/month1/MONTH1_IMPLEMENTATION_PLAN_CURRENT.md` (this file)
- `docs/month1/build_pptx.py`
- `docs/month1/build_pptx_multiturn.py`
- `docs/sockeye/README.md`
- `docs/sockeye/env.example`
- `scripts/sockeye/api_server.slurm`
- `scripts/sockeye/gpu_inference.slurm`

**Runtime data directories (created at run time, not source)**

- `data/sessions/` — JSON session snapshots
- `data/chroma/` — Chroma persistence (default from settings)

## FastAPI endpoints

### `GET /health`

- **Returns**: JSON with `status` (`"ok"`), `service` (app name from settings), and `environment`.

### `POST /api/v1/chat`

- **Request body**: `ChatRequest` — `session_id: str`, `message: str`.
- **Response**: `ChatResponse` — `session_id`, `response` (final assistant text), `citations` (list of `Evidence`: `source`, `snippet`, `score`), `escalated` (bool), optional `safety_reason`.

- **Behavior (summary)**:
  - Rejects empty/whitespace `session_id` with HTTP 400.
  - Invokes the compiled graph with `config["configurable"]["thread_id"] = session_id` so **LangGraph SqliteSaver** resumes prior **checkpoint state** (messages, checklist, encoder fields, etc.) for that thread.
  - Passes a single new **`HumanMessage`** for this turn; **`add_messages`** appends it to the checkpointed transcript.
  - After the run, **`save_session`** writes **audit JSON** (merged checklist + flat transcript) under `data/sessions/`; this is **not** read back by the API (the checkpoint is the source of truth for orchestration).

## LangGraph nodes

Graph is built in `build_chat_graph(checkpointer=...)` with **registered node keys** (first column) mapping to **handler functions** in `app/orchestrator/nodes.py` (second column). Edges are strictly linear:  
`START → preprocess_input → ingest_input → encode_input → retrieve_evidence → generate_draft → policy_gate → finalize_response → END`.

| Graph node key | Python function | Role |
|----------------|-----------------|------|
| `preprocess_input` | `preprocess_input_node` | Sets `message` / `message_normalized` from the **latest** `HumanMessage` in `messages`. |
| `ingest_input` | `ingest_input_node` | No-op placeholder. |
| `encode_input` | `encode_input_node` | Runs `encode_user_message`, **merges** checklist with checkpointed prior rows, sets embeddings and **this-turn-only** `red_flag_hits`. |
| `retrieve_evidence` | `retrieve_evidence_node` | Calls `retrieve_evidence(...)` with normalized text and `encoder_pooled_embedding`; fills `evidence`. |
| `generate_draft` | `generate_draft_node` | Calls `generate_response` with normalized query, evidence, and **history derived from `messages`** (all turns before the latest user). |
| `policy_gate` | `policy_gate_node` | Calls `apply_policy` on draft + `red_flag_hits`; may set `escalated`, `safety_reason`, and override `final_response`. |
| `finalize_response` | `finalize_response_node` | Appends an **`AIMessage`** (final text) to `messages` via the reducer. |

## Month 1 tests (current)

- `test_health_endpoint_returns_ok` (`tests/test_health.py`)
- `test_chat_endpoint_returns_response` (`tests/test_chat_route.py`)
- `test_chat_endpoint_escalates_on_red_flag` (`tests/test_chat_route.py`)
- `test_chat_endpoint_rejects_blank_session_id` (`tests/test_chat_route.py`)
- `test_graph_generates_citations` (`tests/test_graph.py`)
- `test_policy_gate_blocks_unsafe_output` (`tests/test_graph.py`)
- `test_normalize_applies_nfkc_and_case_folding` (`tests/test_preprocess.py`)
- `test_normalize_collapse_whitespace` (`tests/test_preprocess.py`)
- `test_normalize_strips_zero_width` (`tests/test_preprocess.py`)
- `test_empty_and_whitespace_only` (`tests/test_preprocess.py`)
- `test_retrieve_evidence_empty_when_rag_load_false` (`tests/test_rag_toggle.py`)
- `test_session_json_accumulates_transcript` (`tests/test_session_chat.py`)
- `test_merge_checklist_dedupes` (`tests/test_session_chat.py`)
- `test_escalation_drops_when_follow_up_has_no_red_flags` (`tests/test_escalation_session.py`)
- `test_checkpoint_thread_accumulates_messages` (`tests/test_checkpoint_thread.py`)

## Definition of done

- API endpoints run locally without errors (with sensible env defaults or local model paths where applicable).
- Workflow follows the same linear LangGraph order each time.
- All tests under `tests/` pass.
- Responses include citations (possibly empty when RAG is off) and escalation metadata, and sessions optionally persist multi-turn context under `data/sessions`.
