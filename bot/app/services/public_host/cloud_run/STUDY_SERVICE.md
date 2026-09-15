# TRI-BACK public hosting (Cloud Run)

The public link is the **study** Cloud Run URL. The bot stays private; the study UI calls it with a Bearer key.

GitHub: `robdima96/TRI-BACK`. Cloud Build triggers `tri-back-bot-deploy` and `tri-back-study-deploy` deploy image-only updates on push to `main`.

| Role | Cloud Run | URL |
|------|-----------|-----|
| Bot (private) | `tri-back` | `https://tri-back-PLACEHOLDER.us-central1.run.app` |
| Study (public) | `tri-back-study` | `https://tri-back-study-PLACEHOLDER.us-central1.run.app` |
| Artifact Registry | `tri-back` | `tri-back-bot`, `tri-back-study` images |
| GCS bucket | `digimsk-cloudrun-YOUR_GCP_PROJECT` | cannot rename; mounted at `/mnt/tri-back` |

Env vars are `TRI_BACK_*`. Deploy scripts write those names.

Repo root for PowerShell:

```powershell
cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\TRI-BACK"
```

## Deploy bot

```powershell
$env:TRI_BACK_BOT_API_KEY = "…"
.\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1
```

Smoke: `/health` → `"service": "TRI-BACK"`; `/ready` → 200. Direct browser hits should fail (private).

## Deploy study

Study image must be built with `--build-arg PUBLIC_BASE_URL=<the study URL>` or WebSockets break.

```powershell
$env:TRI_BACK_BOT_API_KEY = "…"
$env:TRI_BACK_ADMIN_PASSWORD = "…"
.\bot\app\services\public_host\cloud_run\scripts\deploy_study.ps1
```

Confirm `CHATBOT_BASE_URL` is the bot URL and the study SA has `roles/run.invoker` on `tri-back`.

## Prove the public link

1. Open `https://tri-back-study-PLACEHOLDER.us-central1.run.app`
2. Login page over HTTPS; DevTools: `wss://…/_event` stays up
3. Admin login → one chat turn
4. New file under `gs://digimsk-cloudrun-YOUR_GCP_PROJECT/sessions/`

## Related files

| File | Role |
|------|------|
| `scripts/deploy_bot.ps1` | Bot service `tri-back` |
| `scripts/deploy_study.ps1` | Public UI `tri-back-study` |
| `scripts/upload_gcs_assets.ps1` | GliNER + graph → GCS bucket |
| `Dockerfile.bot` / root `Dockerfile` | Bot image, mount paths `/mnt/tri-back` |
| `Dockerfile.study` | Study image, `COPY prototypes/tri_back_study_app/` |
