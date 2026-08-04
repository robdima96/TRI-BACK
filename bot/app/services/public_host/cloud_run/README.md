# DigiMSK Cloud Run hosting

Git → Cloud Build → Cloud Run for the study UI + bot, using **GCS volume mounts** for:

- GliNER weights  
- Red-flags knowledge graph **v2**  
- Persistent session JSON (`DIGIMSK_SESSION_STORE_DIR`)

Traditional Chroma RAG is **off** on the hosted bot (`DIGIMSK_RAG=0`); GraphRAG stays on.

## Start here

**[STUDY_SERVICE.md](STUDY_SERVICE.md)** — full step-by-step from GCP setup through bot deploy, study Caddy/Reflex finish, and acceptance tests.

## Docs in this folder

| File | Purpose |
|------|---------|
| [STUDY_SERVICE.md](STUDY_SERVICE.md) | **Operator checklist** (Phases A–G) |
| [PLAN.md](PLAN.md) | Architecture, bake vs GCS, ephemeral disk |
| [gcs_layout.md](gcs_layout.md) | Bucket prefixes and env path mapping |
| [.env.cloud.example](.env.cloud.example) | Cloud Run env template |
| [Dockerfile.bot](Dockerfile.bot) | Bot image (ready; no models baked in) |
| [Dockerfile.study](Dockerfile.study) | Study / Reflex image (finish entrypoint in Phase D) |
| [cloudbuild.yaml](cloudbuild.yaml) | Build both images (use after study Dockerfile works) |
| [scripts/upload_gcs_assets.ps1](scripts/upload_gcs_assets.ps1) | Upload GliNER + v2 graph; ensure `sessions/` |
| [scripts/deploy_bot.ps1](scripts/deploy_bot.ps1) | Deploy bot with GCS mounts |

## Short path (bot only)

From DigiMSK monorepo root:

1. `gcloud auth login` / `gcloud config set project YOUR_GCP_PROJECT`  
2. Set `DIGIMSK_BOT_API_KEY` (and optional `DIGIMSK_GCS_BUCKET`).  
3. `.\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1 -GliNERDir "…"`.  
4. Build/push `Dockerfile.bot` → Artifact Registry.  
5. `.\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1` (**max-instances=1**).  
6. Grant runtime SA Storage + smoke `/ready` + one chat → `gs://…/sessions/`.  

Then continue Phase D–F in `STUDY_SERVICE.md` for the public study URL.
