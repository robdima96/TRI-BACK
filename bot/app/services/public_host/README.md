# TRI-BACK public hosting

Shared with the running bot (always):

- `api_auth.py` — Bearer `TRI_BACK_BOT_API_KEY` + chat rate limits on `POST /api/v1/chat`

Local development is unchanged: `uvicorn` on `127.0.0.1:8001`, then Reflex in `prototypes/tri_back_study_app`.
