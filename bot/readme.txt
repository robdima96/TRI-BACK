TRI-BACK — Bot backend
=====================

WHAT IT IS
----------
The chatbot API and orchestration engine. It does NOT serve the study website.
Other apps call it over HTTP:

  POST /api/v1/chat   { "session_id", "message" }
  GET  /health
  GET  /ready

Pipeline (simplified): encode / GliNER checklist -> GraphRAG (red-flags graph) ->
Vertex (or local) generator -> session JSON under data/sessions/.

Optional: TRI_BACK_BOT_API_KEY requires
Authorization: Bearer <key> on /api/v1/chat.


HOW TO RUN LOCALLY
------------------
Prerequisites: Python 3.11+, Vertex ADC if using TRI_BACK_GENERATOR_BACKEND=vertex
  (gcloud auth application-default login).

  cd bot
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -e ".[dev]"
  # Configure bot/.env (Vertex project, TRI_BACK_GRAPH_CSV, model dirs, etc.)
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

Confirm:  http://127.0.0.1:8001/health
          http://127.0.0.1:8001/ready   (wait for warmup; may take 20-40s)


PORTS
-----
8001 — bot API (keep free for the study app; Reflex uses 8000)


RELATED
-------
- Study UI:     ../prototypes/tri_back_study_app/readme.txt
- Session lab:  ../Testing/readme.txt
- Cloud Run:    app/services/public_host/cloud_run/
- Graph packs:  ../Graphs/backups/red flags/  (workspace; used via TRI_BACK_GRAPH_CSV)
