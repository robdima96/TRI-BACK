# TRI-BACK — File Inventory

Short map of **where the main pieces live**. You do not need to open every folder.

## Two main pieces

- **Study website** (`prototypes/tri_back_study_app/`, formerly `tri_back_study_app`) — Login, chat, three display arms, feedback, research logging. Talks only to the bot; does **not** call the AI model itself.
- **Clinical bot** (`bot/`) — Checklist, questions, local evidence, recommendation draft, safety. Vertex (or a local wording model) is used here for phrasing only.

## Inside the bot

- **Checklist intake** — Turn each message into structured facts, then credit answers to the last question asked.
- **Question mode** — Pick the next missing topic; ask **one** follow-up.
- **Disposition mode** — Search local evidence (document library + red-flag graph), draft advice, run safety.
- **Wording model** — Vertex Gemini via bot settings (`vertex` or `local` backend).

## What the study records and shows

- **Arms** — Same bot reply; Arm 1 short text, Arm 2 explanation, Arm 3 graph panel.
- **Sessions** — Study logs in `prototypes/sessions/`; bot copies under `bot/data/sessions/`.
- **Not on the live path** — `Graphs/` explorer tools; `Uncanny Valley/` offline prompt work.

## Settings and ports

- **Wording backend** — `TRI_BACK_GENERATOR_BACKEND` = `vertex` or `local`
- **Vertex project** — `TRI_BACK_VERTEX_PROJECT_ID` (and location); local model folder only if `local`
- **Study app → bot** — usually `http://127.0.0.1:8001`
- **Ports** — chat **3000**, study app **8000**, clinical bot **8001**

Diagrams: `diagrams/02_langgraph_pipeline.mmd` (conversation modes), `diagrams/03_api_map.mmd` (local vs AI model).
