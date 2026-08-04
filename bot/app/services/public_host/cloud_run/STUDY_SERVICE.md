# DigiMSK public hosting — step-by-step (Cloud Run + GCS)

## If your first Console build failed (read this first)

You connected GitHub → Cloud Run continuous deploy. That trigger builds with:

```text
docker build -f Dockerfile .
```

at the **repo root**. Until today there was **no** root `Dockerfile`, so build `83f808a4-…` failed in a few seconds.

**What to do next (Console path you already started):**

1. **Push the root `Dockerfile`** (bot image). Ask the agent to commit/push, or:

```powershell
cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot"
git add Dockerfile
git commit -m "Add root Dockerfile so Cloud Run continuous deploy can build the bot."
git push origin main
```

2. In Cloud Console → **Cloud Build → History**, wait for the new build on `main` to go **SUCCESS**.  
   Service name from your trigger is **`digimskbot`** (fine — use that name going forward for the bot).

3. **A successful image build is not enough.** The auto-deployed service still needs GCS assets + mounts + secrets (GliNER, graph, sessions). Do this **once** after the first green build:

```powershell
cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot"

# Upload GliNER + graph v2 into the bucket (edit -GliNERDir if needed)
.\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1 `
  -GliNERDir "E:\DigiMSKbot\GliNER-BioMed"

# Put API key in the shell, then attach bucket + env to the EXISTING Console service
$env:DIGIMSK_BOT_API_KEY = "paste-your-long-random-key-here"
.\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1 -Service digimskbot
```

`deploy_bot.ps1` re-deploys the **same** image tag with `/mnt/digimsk` mount, GraphRAG env, and `max-instances=1`. After that, smoke-test `/health` and `/ready` (Phase C4 below).

4. **Do not** create a second “study” continuous-deploy from Console yet — the study Dockerfile is still unfinished.

---

## Big picture

```text
Browser  →  digimsk-study (public HTTPS + WebSocket /_event)   ← later
               │  httpx + Bearer DIGIMSK_BOT_API_KEY
               ▼
            digimskbot (or digimsk-bot) — private bot API
               │  GCS mount /mnt/digimsk  (GliNER, graph v2, sessions/)
               ▼
            Vertex AI (same GCP project)
```

**Repo root** for PowerShell:

```powershell
cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot"
```

| App | Folder | Cloud Run service |
|-----|--------|-------------------|
| Bot backend | `bot/` | `digimskbot` (your Console name) or `digimsk-bot` |
| Study UI | `prototypes/digimsk_study_app/` | `digimsk-study` (later) |
| Session lab | `Testing/` | **local only** — do not host |

---

## What is already done in Git

- [x] Monorepo with three apps + Cloud Run kit  
- [x] Bot API Bearer auth (`DIGIMSK_BOT_API_KEY`) + rate limits  
- [x] Root `Dockerfile` + `Dockerfile.bot` (same bot image)  
- [x] `deploy_bot.ps1`, `upload_gcs_assets.ps1`, `cloudbuild.yaml`  
- [x] Hosted defaults: GraphRAG on, Chroma RAG off, sessions on GCS, `max-instances=1`  
- [ ] You: green Console build → upload GCS → `deploy_bot.ps1 -Service digimskbot` → smoke → study later  

---

## Phase A — One-time GCP setup

### A1. Tools and login

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_GCP_PROJECT
```

Confirm APIs (enable any that fail): Cloud Run, Cloud Build, Artifact Registry, Cloud Storage, Vertex AI, Secret Manager (optional).

### A2. Artifact Registry repo (once)

```powershell
gcloud artifacts repositories create digimsk `
  --repository-format=docker `
  --location=us-central1 `
  --description="DigiMSK bot and study images"
```

Ignore “already exists”. Then:

```powershell
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### A3. Secrets (recommended)

Create two secrets (or keep values only in your local shell / Secret Manager UI — **do not commit**):

| Secret | Used by |
|--------|---------|
| `DIGIMSK_BOT_API_KEY` | bot + study (same value) |
| `DIGIMSK_ADMIN_PASSWORD` | study login only |

```powershell
# Example: create from stdin (PowerShell)
"YOUR_LONG_RANDOM_BOT_KEY" | gcloud secrets create DIGIMSK_BOT_API_KEY --data-file=-
"YOUR_STRONG_ADMIN_PASSWORD" | gcloud secrets create DIGIMSK_ADMIN_PASSWORD --data-file=-
```

For deploy scripts you can also set session env vars once:

```powershell
$env:DIGIMSK_BOT_API_KEY = "YOUR_LONG_RANDOM_BOT_KEY"
$env:DIGIMSK_GCS_BUCKET = "digimsk-cloudrun-YOUR_GCP_PROJECT"
$env:DIGIMSK_GCP_PROJECT = "YOUR_GCP_PROJECT"
```

---

## Phase B — Upload assets to GCS

### B1. Confirm local sources

| Asset | Local path |
|-------|------------|
| Graph CSV | `Graphs\backups\red flags\v2\source\red_flags_manual_v2.csv` |
| Inventory | `Graphs\backups\red flags\v2\inventory.json` |
| GliNER | Your model tree (default script path: `E:\DigiMSKbot\GliNER-BioMed`) |

### B2. Run upload

```powershell
.\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1 `
  -GliNERDir "E:\DigiMSKbot\GliNER-BioMed"
```

Creates bucket `gs://digimsk-cloudrun-YOUR_GCP_PROJECT` if needed and fills:

```text
models/gliner/
graph/v2/red_flags_manual_v2.csv
graph/v2/inventory.json
sessions/.keep
```

Layout details: [gcs_layout.md](gcs_layout.md).

### B3. Spot-check

```powershell
gcloud storage ls gs://digimsk-cloudrun-YOUR_GCP_PROJECT/graph/v2/
gcloud storage ls gs://digimsk-cloudrun-YOUR_GCP_PROJECT/models/gliner/ | Select-Object -First 20
```

---

## Phase C — Build and deploy the **bot**

Do **not** run full `cloudbuild.yaml` yet if the study Dockerfile still exits on purpose (Phase E). Build **bot only**.

### C1. Build and push bot image

**Option — local Docker:**

```powershell
docker build `
  -f bot/app/services/public_host/cloud_run/Dockerfile.bot `
  -t us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-bot:latest `
  .

docker push us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-bot:latest
```

**Option — Cloud Build (bot only):**

```powershell
gcloud builds submit `
  --tag us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-bot:latest `
  --dockerfile bot/app/services/public_host/cloud_run/Dockerfile.bot `
  .
```

If your `gcloud` version rejects `--dockerfile`, use a one-off config that only builds the bot, or build with Docker locally (above).
### C2. Deploy bot with GCS mount

```powershell
$env:DIGIMSK_BOT_API_KEY = "YOUR_LONG_RANDOM_BOT_KEY"   # if not already set
.\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1
```

That script sets GraphRAG-only env, mounts the bucket at `/mnt/digimsk`, **`max-instances=1`**, **`--no-allow-unauthenticated`**, checkpoints on `/tmp`.

### C3. IAM after first deploy

1. Note the bot **runtime service account** (Cloud Run → service → Security), often  
   `xxxxx-compute@developer.gserviceaccount.com`.
2. Grant bucket access (object read + session write):

```powershell
$sa = "SERVICE_ACCOUNT_EMAIL_HERE"
$bucket = "digimsk-cloudrun-YOUR_GCP_PROJECT"
gcloud storage buckets add-iam-policy-binding "gs://$bucket" `
  --member="serviceAccount:$sa" `
  --role="roles/storage.objectUser"
```

3. Ensure the same SA can call Vertex (`roles/aiplatform.user` on the project) — usually already true if you use the default compute SA in this Vertex project.

### C4. Smoke-test the bot

Cloud Run IAM and DigiMSK Bearer both use `Authorization`. Easiest smoke path: briefly allow unauthenticated invoke, test Bearer-only, then lock the service again (study will get `roles/run.invoker` in Phase E).

```powershell
$BOT = "https://digimsk-bot-XXXXX.us-central1.run.app"   # from deploy output

gcloud run services add-iam-policy-binding digimsk-bot `
  --region=us-central1 `
  --member="allUsers" `
  --role="roles/run.invoker"

curl.exe -s "$BOT/health"
curl.exe -s "$BOT/ready"    # GliNER warmup — can take 30–90s on cold start

# Without DigiMSK key → expect 401
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$BOT/api/v1/chat" `
  -H "Content-Type: application/json" `
  -d '{"session_id":"smoke","message":"hello"}'

# With DigiMSK key → expect a normal chat response
curl.exe -s -X POST "$BOT/api/v1/chat" `
  -H "Authorization: Bearer YOUR_LONG_RANDOM_BOT_KEY" `
  -H "Content-Type: application/json" `
  -d '{"session_id":"smoke1","message":"I have low back pain for 2 weeks"}'
gcloud run services remove-iam-policy-binding digimsk-bot `
  --region=us-central1 `
  --member="allUsers" `
  --role="roles/run.invoker"
```

Confirm a new object under `gs://…/sessions/` after a successful chat.

**Stop here until `/ready` is true and a session JSON appears.** Study hosting depends on a working bot URL + key.

---

## Phase D — Decide study production entry (code change)

Cloud Run needs **one** listener on `0.0.0.0:$PORT` (usually 8080).  
Local Reflex uses **two** ports (UI `:3000`, backend/WS `:8000`). DigiMSK needs WebSocket `/_event` (plain static export alone is not enough).

### D1. Finish `Dockerfile.study`

Current image intentionally fails at start. Replace the placeholder `CMD` so the container:

1. Starts Reflex (production mode) with backend on `127.0.0.1:8000` and frontend on `127.0.0.1:3000` (or the equivalent for your Reflex version).  
2. Runs **Caddy** (or nginx) as the process bound to `$PORT` that:
   - upgrades `/_event*` → `127.0.0.1:8000` (WebSocket)
   - proxies everything else → `127.0.0.1:3000`
3. Installs Node if required by `reflex run` / export on that image.

Example Caddy sketch (adapt paths/ports to what Reflex actually binds):

```caddy
:{$PORT} {
  handle /_event* {
    reverse_proxy 127.0.0.1:8000
  }
  handle {
    reverse_proxy 127.0.0.1:3000
  }
}
```

`rxconfig.py` already respects `DIGIMSK_PUBLIC_ACCESS=1` + `DIGIMSK_PUBLIC_BASE_URL` for `api_url` / CORS.

### D2. Study SQLite on Cloud Run

Container disk is ephemeral. For v1:

- Mount the **same** GCS bucket (or a second bucket) and set e.g.  
  `DIGIMSK_STUDY_DB=/mnt/digimsk/study/digimsk.db`  
- Keep **`max-instances=1`** on `digimsk-study` until Cloud SQL.  
- Seed users once (local or Cloud Run Job): `generate_roster` → `init_db` → `seed_users`, writing the DB into GCS before inviting participants.

Chat **session JSON** stays on the bot mount (`/mnt/digimsk/sessions`), not the study DB.

---

## Phase E — Build and deploy **study**

### E1. Build / push study image (after D1 works locally in Docker)

```powershell
docker build `
  -f bot/app/services/public_host/cloud_run/Dockerfile.study `
  -t us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-study:latest `
  .

docker push us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/digimsk/digimsk-study:latest
```

Or full monorepo Cloud Build (bot + study) once both Dockerfiles succeed:

```powershell
gcloud builds submit --config bot/app/services/public_host/cloud_run/cloudbuild.yaml .
```

### E2. First deploy (public UI)

Replace `YOUR-BOT-URL` with the real `digimsk-bot` HTTPS URL from Phase C.

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
  --add-volume=name=digimsk-gcs,type=cloud-storage,bucket=digimsk-cloudrun-YOUR_GCP_PROJECT `
  --add-volume-mount=volume=digimsk-gcs,mount-path=/mnt/digimsk `
  --set-env-vars="DIGIMSK_PUBLIC_ACCESS=1,CHATBOT_BASE_URL=https://YOUR-BOT-URL.run.app,DIGIMSK_BOT_API_KEY=YOUR_LONG_RANDOM_BOT_KEY,DIGIMSK_ADMIN_PASSWORD=YOUR_STRONG_ADMIN_PASSWORD,DIGIMSK_STUDY_DB=/mnt/digimsk/study/digimsk.db"
```

### E3. Set public base URL to the printed study URL

```powershell
$STUDY = "https://digimsk-study-XXXXX.us-central1.run.app"
gcloud run services update digimsk-study --region=us-central1 `
  --update-env-vars="DIGIMSK_PUBLIC_BASE_URL=$STUDY,API_URL=$STUDY,DEPLOY_URL=$STUDY"
```

### E4. Study runtime SA → storage + bot invoke

Grant study SA `roles/storage.objectUser` on the bucket (same as bot) if using study SQLite on GCS.

Grant study SA permission to call the private bot:

```powershell
$studySa = "STUDY_RUNTIME_SA_EMAIL"
gcloud run services add-iam-policy-binding digimsk-bot `
  --region=us-central1 `
  --member="serviceAccount:$studySa" `
  --role="roles/run.invoker"
```

Study must still send `Authorization: Bearer <DIGIMSK_BOT_API_KEY>` on `/api/v1/chat` (already wired in the study HTTP client when the env is set).

---

## Phase F — Acceptance tests

1. Open the study URL — login page loads over HTTPS.  
2. DevTools → Network: `wss://…/_event` stays connected (no flap).  
3. Admin login with `DIGIMSK_ADMIN_PASSWORD`; complete one chat turn.  
4. New JSON under `gs://…/sessions/`.  
5. Direct browser hit to bot URL without credentials fails; chat without Bearer fails.  
6. Optional: participant login from seeded credentials.

---

## Phase G — Optional continuous deploy from Git

1. Cloud Build trigger on `robdima96/DigiMSKbot` → `main`  
2. Config: `bot/app/services/public_host/cloud_run/cloudbuild.yaml`  
3. Build context: **repository root** (must see `bot/` and `prototypes/`)  
4. After image push, either:
   - re-run `deploy_bot.ps1` / study `gcloud run deploy`, or  
   - add deploy steps / Cloud Deploy once images are trusted  

Volume mounts and secrets stay on **deploy**, not inside the Dockerfile.

---

## Practical order (short)

1. **A** GCP login + Artifact Registry + secrets  
2. **B** `upload_gcs_assets.ps1`  
3. **C** Build/push **bot** → `deploy_bot.ps1` → IAM → `/ready` + session smoke  
4. **D** Caddy + Reflex entry in `Dockerfile.study` + study DB path  
5. **E** Build/push **study** → deploy public → set `DIGIMSK_PUBLIC_BASE_URL` → invoker on bot  
6. **F** WebSocket + login + chat acceptance  
7. **G** Cloud Build trigger when stable  

---

## Related files

| File | Role |
|------|------|
| [README.md](README.md) | Index of this folder |
| [PLAN.md](PLAN.md) | Why GCS mounts, GraphRAG-only, max-instances |
| [gcs_layout.md](gcs_layout.md) | Bucket prefixes ↔ env vars |
| [.env.cloud.example](.env.cloud.example) | Bot env template |
| [scripts/upload_gcs_assets.ps1](scripts/upload_gcs_assets.ps1) | Upload GliNER + graph v2 |
| [scripts/deploy_bot.ps1](scripts/deploy_bot.ps1) | Deploy bot + mount |
| [Dockerfile.bot](Dockerfile.bot) | Ready |
| [Dockerfile.study](Dockerfile.study) | Skeleton until Phase D |
