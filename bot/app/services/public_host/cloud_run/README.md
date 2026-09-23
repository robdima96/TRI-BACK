# TRI-BACK Cloud Run hosting

Git → Cloud Build → Cloud Run for the study UI + bot, using **GCS volume mounts** for:

- GliNER weights  
- Red-flags knowledge graph **v2**  
- Persistent session JSON (`TRI_BACK_SESSION_STORE_DIR`)

Traditional Chroma RAG is **off** on the hosted bot (`TRI_BACK_RAG=0`); GraphRAG stays on.

## Start here

**[STUDY_SERVICE.md](STUDY_SERVICE.md)** — full step-by-step from GCP setup through bot deploy, study Caddy/Reflex finish, and acceptance tests.

## Docs in this folder

| File | Purpose |
|------|---------|
| [STUDY_SERVICE.md](STUDY_SERVICE.md) | **Operator checklist** (new `tri-back` / `tri-back-study` services) |
| [PLAN.md](PLAN.md) | Architecture, bake vs GCS, ephemeral disk |
| [gcs_layout.md](gcs_layout.md) | Bucket prefixes and env path mapping |
| [.env.cloud.example](.env.cloud.example) | Cloud Run env template |
| [Dockerfile.bot](Dockerfile.bot) | Bot image (ready; no models baked in) |
| [Dockerfile.study](Dockerfile.study) | Study / Reflex + Caddy one-port image |
| [Caddyfile.study](Caddyfile.study) | Proxy `/_event` + static `/srv` |
| [cloudbuild.bot.yaml](cloudbuild.bot.yaml) | Build/push/**deploy** bot (`tri-back-bot-deploy` trigger) |
| [cloudbuild.study.yaml](cloudbuild.study.yaml) | Build/push/**deploy** study (`tri-back-study-deploy` trigger) |
| [scripts/upload_gcs_assets.ps1](scripts/upload_gcs_assets.ps1) | Upload GliNER + v2 graph; ensure `sessions/` |
| [scripts/deploy_bot.ps1](scripts/deploy_bot.ps1) | Deploy bot with GCS mounts (default service `tri-back`) |
| [scripts/deploy_study.ps1](scripts/deploy_study.ps1) | Deploy public study UI wired to bot |
| [scripts/entrypoint_study.sh](scripts/entrypoint_study.sh) | Container start: Redis → Reflex → Caddy |

## Short path (bot only)

From the TRI-BACK monorepo root:

1. `gcloud auth login` / `gcloud config set project $env:TRI_BACK_GCP_PROJECT`  
2. Set `TRI_BACK_GCP_PROJECT`, `TRI_BACK_GCS_BUCKET`, `TRI_BACK_RUNTIME_SA`. Create Secret Manager secrets `TRI_BACK_BOT_API_KEY` (and for the study service, `TRI_BACK_ADMIN_PASSWORD`).  
3. `.\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1 -GliNERDir "…"`.  
4. Build/push `Dockerfile.bot` → Artifact Registry `tri-back/tri-back-bot`.  
5. `.\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1` (**max-instances=1**).  
6. Grant runtime SA Storage + smoke `/ready` + one chat → `gs://…/sessions/`.  

Then continue in `STUDY_SERVICE.md` for the public study URL.
