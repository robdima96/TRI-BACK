# TRI-BACK public hosting — Cloud Run cutover (from DigiMSK)

The public link is the **study** Cloud Run URL. The bot stays private; the study UI calls it with a Bearer key.

Cloud Run services **cannot be renamed**. This cutover creates **new** services beside the old ones, remounts the **same** GCS bucket at `/mnt/tri-back`, then you delete the old names after smoke tests.

| Role | Old | New |
|------|-----|-----|
| Bot (private) | `digimskbot` | `tri-back` |
| Study (public) | `digimsk-study` | `tri-back-study` |
| Artifact Registry | `digimsk` / `digimsk-bot`, `digimsk-study` | `tri-back` / `tri-back-bot`, `tri-back-study` |
| GCS bucket | `digimsk-cloudrun-YOUR_GCP_PROJECT` | **keep** (cannot rename) |
| Mount | `/mnt/digimsk` | `/mnt/tri-back` |
| Secrets | `DIGIMSK_BOT_API_KEY`, `DIGIMSK_ADMIN_PASSWORD` | `TRI_BACK_BOT_API_KEY`, `TRI_BACK_ADMIN_PASSWORD` (same payload) |

Env vars: code prefers `TRI_BACK_*` and still reads `DIGIMSK_*`. Deploy scripts write `TRI_BACK_*`.

GitHub repo is `robdima96/TRI-BACK`. Cloud Build triggers `tri-back-bot-deploy` and `tri-back-study-deploy` track that name.

Repo root for PowerShell:

```powershell
cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot"
```

## 1. One-time GCP objects

```powershell
gcloud config set project YOUR_GCP_PROJECT
gcloud artifacts repositories create tri-back `
  --repository-format=docker --location=us-central1 `
  --description="TRI-BACK bot and study images"

# Same values as today's DIGIMSK_* secrets
"YOUR_EXISTING_BOT_KEY" | gcloud secrets create TRI_BACK_BOT_API_KEY --data-file=-
"YOUR_EXISTING_ADMIN_PW" | gcloud secrets create TRI_BACK_ADMIN_PASSWORD --data-file=-
```

Ignore “already exists”. Do **not** create a new GCS bucket.

## 2. Deploy the new bot (`tri-back`)

Build/push `us-central1-docker.pkg.dev/YOUR_GCP_PROJECT/tri-back/tri-back-bot:latest` (Cloud Build `cloudbuild.yaml` or local Docker), then:

```powershell
$env:TRI_BACK_BOT_API_KEY = "same-key-as-today"
.\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1
# Old name:  .\...\deploy_bot.ps1 -Service digimskbot
```

Smoke: `https://tri-back-….run.app/health` → `"service": "TRI-BACK"`; `/ready` → 200. Direct browser hits should fail (private).

## 3. Deploy the new study (`tri-back-study`) — new public link

Study image must be built with `--build-arg PUBLIC_BASE_URL=<the new study URL>`. Reflex bakes that into the frontend.

1. First deploy prints the new URL (`deploy_study.ps1`).
2. Rebuild/push the study image with that URL as `PUBLIC_BASE_URL` (or set `_PUBLIC_BASE_URL` on `cloudbuild.study.yaml`).
3. Redeploy `tri-back-study`.
4. Confirm `CHATBOT_BASE_URL` is the new bot URL and the study SA has `roles/run.invoker` on `tri-back`.

```powershell
$env:TRI_BACK_BOT_API_KEY = "same-key-as-today"
$env:TRI_BACK_ADMIN_PASSWORD = "same-admin-as-today"
.\bot\app\services\public_host\cloud_run\scripts\deploy_study.ps1
# Old names: -Service digimsk-study -BotService digimskbot
```

## 4. Prove the public link

1. Open `https://tri-back-study-….us-central1.run.app`
2. Login page over HTTPS; DevTools: `wss://…/_event` stays up
3. Admin login → one chat turn
4. New file under `gs://digimsk-cloudrun-…/sessions/`

Keep `https://tri-back-study-PLACEHOLDER-uc.a.run.app` up until nobody uses it.

Live cutover URLs (2026-09-13):

- Bot (private): `https://tri-back-PLACEHOLDER.us-central1.run.app`
- Study (public): `https://tri-back-study-PLACEHOLDER.us-central1.run.app`

## 5. GitHub last (after the new Cloud Run pair is healthy)

Repo is `robdima96/TRI-BACK`. Local remote:

```powershell
git remote set-url origin https://github.com/robdima96/TRI-BACK.git
git remote -v
```

Cloud Build GitHub triggers (push to `main`):

| Trigger | Config | Deploys |
|---------|--------|---------|
| `tri-back-bot-deploy` | `cloudbuild.bot.yaml` | `tri-back` (image-only) |
| `tri-back-study-deploy` | `cloudbuild.study.yaml` | `tri-back-study` (image-only) |

GitHub App is connected to `robdima96/TRI-BACK`. GitHub triggers use repo-root `.gcloudignore` (must include `bot/app` and `prototypes/tri_back_study_app`). Manual bot submits can still pass `--ignore-file=.gcloudignore.bot`.

Disabled leftovers (do not re-enable): `digimsk-study-deploy`, `rmgpgab-digimskbot-us-central1-robdima96-DigiMSKbot--macqx`. Root `Dockerfile` stays in lockstep with `Dockerfile.bot` for any Cloud Run CD leftover.

## 6. Tear down old names (later)

When the old study URL is unused: delete Cloud Run `digimskbot` and `digimsk-study`; optionally delete Artifact Registry `digimsk`. Keep the GCS bucket until an explicit copy/cut.

## Related files

| File | Role |
|------|------|
| `scripts/deploy_bot.ps1` | New bot service (default `tri-back`; `-Service digimskbot` override) |
| `scripts/deploy_study.ps1` | New public UI (default `tri-back-study`) |
| `scripts/upload_gcs_assets.ps1` | GliNER + graph → existing bucket |
| `Dockerfile.bot` / root `Dockerfile` | Bot image, mount paths `/mnt/tri-back` |
| `Dockerfile.study` | Study image, `COPY prototypes/tri_back_study_app/` |
