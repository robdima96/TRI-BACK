# DigiMSKbot (Month 1)

This scaffold provides a practical Month 1 baseline:

- FastAPI service with health and chat endpoints
- LangGraph orchestration with **SQLite checkpoints** (`thread_id` = `session_id`) and **first-class `messages` state** (append reducer); JSON under `data/sessions/` is still written each turn for logging/audit.
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

## Month 1 deliverables

See `docs/month1/MONTH1_IMPLEMENTATION_PLAN.md`.

## UBC ARC Sockeye (compute cluster)

To run on **Sockeye**, see **`docs/sockeye/README.md`**: **submit jobs from `/scratch/<allocation>/`** (not `/arc/home`), partitions (`gpu`, `interactive_*`), hostnames (`sockeye.arc.ubc.ca`, `dtn.sockeye.arc.ubc.ca`, Globus `ubcarc#sockeye`), and Slurm templates under `scripts/sockeye/`. Confluence: [Running Jobs](https://confluence.it.ubc.ca/spaces/UARC/pages/318409964/Running+Jobs), [Software](https://confluence.it.ubc.ca/spaces/UARC/pages/187507341/Software), [About Sockeye](https://confluence.it.ubc.ca/spaces/UARC/pages/319206082/About+Sockeye); [ARC overview](https://arc.ubc.ca/compute-storage/ubc-arc-sockeye).
