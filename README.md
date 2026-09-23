# TRI-BACK

TRI-BACK is software from the **DigiMSK Lab**, Department of Physical Therapy, Faculty of Medicine, University of British Columbia. It is a prototype for low-back virtual triage designed for research purposes. It is not a medical device and does not provide a diagnosis.

Three apps in one project:

| App | Folder | Role |
|-----|--------|------|
| **Bot backend** | [`bot/`](bot/) | FastAPI + LangGraph chatbot API |
| **Study prototype** | [`prototypes/tri_back_study_app/`](prototypes/tri_back_study_app/) | Reflex UI (login, chat, admin) |
| **Session lab** | [`Testing/`](Testing/) | Local browser for session JSON |

Each app has a **`readme.txt`** with local run details. Environment variables use the `TRI_BACK_*` prefix.

## Local use (admin)

1. Copy [`prototypes/tri_back_study_app/.env.example`](prototypes/tri_back_study_app/.env.example) to `.env` in that folder. Set `TRI_BACK_ADMIN_PASSWORD` to a password you choose. Keep `CHATBOT_BASE_URL=http://127.0.0.1:8001`.
2. In `bot/.env`, set `TRI_BACK_ALLOW_OPEN_API=1` so local chat works without an API key. Add your Vertex / graph / model settings as described in `bot/readme.txt`.
3. Start the **bot** on port **8001** (see `bot/readme.txt`). Wait until `http://127.0.0.1:8001/ready` is up.
4. Start the **study prototype** (see `prototypes/tri_back_study_app/readme.txt`) — UI **3000**.
5. Open http://localhost:3000 and sign in on the **Admin** tab (username `admin`, password from your `.env`).

The study app creates an empty local database on first start. Optional: **Session lab** on port **8765** (`Testing/readme.txt`).

## License

Copyright The University of British Columbia (DigiMSK Lab). Licensed under the Apache License, Version 2.0. See [`LICENSE`](LICENSE).
