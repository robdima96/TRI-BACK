# DigiMSK public hosting

**Hosted path:** Google Cloud Run + GCS mounts — see [`cloud_run/`](cloud_run/).

Shared with the running bot (always):

- `api_auth.py` — Bearer `DIGIMSK_BOT_API_KEY` + chat rate limits on `POST /api/v1/chat`

Local development is unchanged: `uvicorn` on `127.0.0.1:8001`, then Reflex in `prototypes/digimsk_study_app` (sibling folder outside this git repo).
