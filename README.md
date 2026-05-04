# DigiMSKbot (Month 1)

This scaffold provides a practical Month 1 baseline:

- FastAPI service with health and chat endpoints
- LangGraph orchestration with **SQLite checkpoints** (`thread_id` = `session_id`) and **first-class `messages` state** (append reducer); JSON under `data/sessions/` written each turn for logging/audit.
- RAG, generation, and policy stubs
- Tests for API routes and orchestration flow

## Quick start

1. Install dependencies:
   - `pip install -e .[dev]`
2. Run the API:
   - `uvicorn app.main:app --reload`
3. Run tests:
   - `pytest`

## Endpoints

- `GET /health` - service health.
- `POST /api/v1/chat` - run one orchestrated chatbot turn (`configurable.thread_id` is the request `session_id`). Optional env: `DIGIMSK_CHECKPOINT_SQLITE` (default `data/langgraph_checkpoints.sqlite`).


