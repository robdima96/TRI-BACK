# Finish the DigiMSK **study** Cloud Run service (step-by-step)

The **bot** and **study** packaging live in this monorepo:

```text
DigiMSK/
  bot/                              <- FastAPI backend
  prototypes/digimsk_study_app/     <- Reflex study UI
  Testing/                          <- session lab for developers
  Graphs/backups/red flags/v2/      <- graph CSV source (upload to GCS)
```

Git remote: the DigiMSK workspace root (contains all three apps).

This checklist assumes the bot is (or will be) deployed with GCS mounts as in `deploy_bot.ps1`.

---

## 0. Prerequisites

- [ ] GCP project `YOUR_GCP_PROJECT` with billing, Cloud Run, Cloud Build, Artifact Registry, Vertex AI enabled  
- [ ] `gcloud auth login` and `gcloud config set project YOUR_GCP_PROJECT`  
- [ ] GCS bucket populated (`upload_gcs_assets.ps1`)  
- [ ] `digimsk-bot` Cloud Run service deployed and `/health` works with an authenticated call  
- [ ] Shared secret `DIGIMSK_BOT_API_KEY` (Secret Manager recommended)  
- [ ] Admin password `DIGIMSK_ADMIN_PASSWORD` for study login  

---

## 1. Build context (monorepo)

Build from the DigiMSK workspace root (contains `bot/`, `prototypes/`, `Testing/`):

```powershell
cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot"
docker build -f bot/app/services/public_host/cloud_run/Dockerfile.study -t digimsk-study .
```

Cloud Build: submit with `bot/app/services/public_host/cloud_run/cloudbuild.yaml` from that same root.

---

## 2. Make Reflex listen on Cloud Run’s `$PORT` (one origin)

Cloud Run expects **one** process listening on `0.0.0.0:$PORT` (usually 8080).

Locally Reflex uses **two** ports (UI `:3000`, backend/WS `:8000`). On Cloud Run you must:

1. Run Reflex in a production-friendly mode (or `reflex export` + static host — only if WS still works for your Reflex version; DigiMSK needs `/_event`).  
2. Put **Caddy** or **nginx** in the container as PID 1 on `$PORT`:
   - `/_event*` → Reflex backend `127.0.0.1:8000` (WebSocket upgrade)  
   - everything else → frontend `127.0.0.1:3000`  
3. Set at **container start** (after you know the Cloud Run URL, or via env):

```text
DIGIMSK_PUBLIC_ACCESS=1
DIGIMSK_PUBLIC_BASE_URL=https://digimsk-study-xxxxx.run.app
API_URL=https://digimsk-study-xxxxx.run.app
DEPLOY_URL=https://digimsk-study-xxxxx.run.app
CHATBOT_BASE_URL=https://digimsk-bot-xxxxx.run.app
DIGIMSK_BOT_API_KEY=<same as bot>
DIGIMSK_ADMIN_PASSWORD=<strong password>
```

`rxconfig.py` already turns on public `api_url` / CORS when `DIGIMSK_PUBLIC_ACCESS=1` and base URL are set.

**Replace** the placeholder `CMD` in `Dockerfile.study` with something like: start Reflex backend + frontend (or single prod server) + Caddy on `$PORT`.

---

## 3. Study database on Cloud Run

Study SQLite (`DIGIMSK_STUDY_DB`) is also ephemeral if left inside the container.

- **v1 simple:** mount the **same** GCS bucket (or a second prefix) read/write at e.g. `/mnt/study-data` and set `DIGIMSK_STUDY_DB=/mnt/study-data/digimsk.db`, **max-instances=1** for the study service too until you move to Cloud SQL.  
- Seed users: run `generate_roster` / `seed_users` in a one-off Cloud Run Job or local script that writes the DB into GCS before first traffic.

Session **chat** logs remain on the bot’s `/mnt/digimsk/sessions` (already planned).

---

## 4. Build and push the study image

```powershell
# After Option A or from workspace root (Option B):
gcloud auth configure-docker us-central1-docker.pkg.dev

# Create Artifact Registry repo once:
gcloud artifacts repositories create digimsk --repository-format=docker --location=us-central1

docker build -f <path-to>/Dockerfile.study -t us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-study:latest .
docker push us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-study:latest
```

---

## 5. Deploy `digimsk-study` to Cloud Run

```powershell
gcloud run deploy digimsk-study `
  --project=YOUR_GCP_PROJECT `
  --region=us-central1 `
  --image=us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-study:latest `
  --memory=2Gi `
  --cpu=2 `
  --max-instances=1 `
  --timeout=3600 `
  --allow-unauthenticated `
  --set-env-vars="DIGIMSK_PUBLIC_ACCESS=1,CHATBOT_BASE_URL=https://YOUR-BOT-URL.run.app,DIGIMSK_BOT_API_KEY=YOUR_KEY,DIGIMSK_ADMIN_PASSWORD=YOUR_ADMIN_PW"
```

Then set public URL env to the **printed study URL** (or custom domain) and redeploy/update:

```powershell
gcloud run services update digimsk-study --region=us-central1 `
  --update-env-vars="DIGIMSK_PUBLIC_BASE_URL=https://YOUR-STUDY-URL.run.app,API_URL=https://YOUR-STUDY-URL.run.app,DEPLOY_URL=https://YOUR-STUDY-URL.run.app"
```

If the study needs GCS for SQLite:

```powershell
gcloud run services update digimsk-study --region=us-central1 `
  --add-volume=name=study-gcs,type=cloud-storage,bucket=YOUR_BUCKET `
  --add-volume-mount=volume=study-gcs,mount-path=/mnt/digimsk
```

(Use a dedicated prefix/DB path so you don’t clash with bot session files carelessly.)

Allow the study runtime SA to **invoke** `digimsk-bot` if the bot is `--no-allow-unauthenticated` (Cloud Run invoker role), **or** keep bot callable with only the shared Bearer key over HTTPS.

---

## 6. Wire bot ↔ study auth

1. Bot has `DIGIMSK_BOT_API_KEY` set.  
2. Study has the **same** key and `CHATBOT_BASE_URL` pointing at the bot service URL.  
3. Grant study SA `roles/run.invoker` on `digimsk-bot` if IAM auth is required in addition to Bearer.

---

## 7. Acceptance tests

1. Open `https://digimsk-study-….run.app` — login page loads.  
2. Browser Network: `wss://…/_event` stays connected (not flapping).  
3. Admin login with `DIGIMSK_ADMIN_PASSWORD`; send a chat turn.  
4. Bot logs / GCS `sessions/` gain a new JSON file.  
5. Unauthenticated browser call to bot URL without key fails.

---

## 8. Optional: continuous deploy from Git

- **Bot:** Cloud Build trigger on `robdima96/DigiMSKbot` using `app/services/public_host/cloud_run/cloudbuild.yaml` (already bot-only).  
- **Study:** either add study sources to that repo (Option A) and extend `cloudbuild.yaml`, or Connect repo / trigger on a second study repository.

---

## Order of work (practical)

1. Deploy and smoke-test **bot** (`upload_gcs_assets` → build → `deploy_bot.ps1`).  
2. Choose Option A or B for study sources.  
3. Implement Caddy + Reflex entry in `Dockerfile.study`.  
4. Deploy study → set public URL env → test WebSocket + login + chat.  
5. Add Cloud Build trigger(s) for push-to-deploy.
