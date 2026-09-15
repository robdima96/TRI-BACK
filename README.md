# TRI-BACK

Three apps in one project for musculoskeletal triage chatbot research.

| App | Folder | Role |
|-----|--------|------|
| **Bot backend** | [`bot/`](bot/) | FastAPI + LangGraph chatbot API (inference, GraphRAG, Vertex, session JSON) |
| **Study prototype** | [`prototypes/tri_back_study_app/`](prototypes/tri_back_study_app/) | Reflex UI for the research study (login, arms, admin) |
| **Session lab** | [`Testing/`](Testing/) | Local browser for developers to inspect `bot/data/sessions` |

Each app has a **`readme.txt`** with what it does and how to run it locally.

## Typical local order

1. Start the **bot** (see `bot/readme.txt`) — port **8001**
2. Start the **study prototype** (see `prototypes/tri_back_study_app/readme.txt`) — UI **3000**
3. Optional: **Session lab** (see `Testing/readme.txt`) — port **8765**

## Hosting

Cloud Run + GCS packaging lives under `bot/app/services/public_host/cloud_run/`.
Cutover from TRI-BACK service names: see [`STUDY_SERVICE.md`](bot/app/services/public_host/cloud_run/STUDY_SERVICE.md).

Env vars are `TRI_BACK_*`.
