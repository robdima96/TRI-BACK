# DigiMSK Cloud Run hosting

Git → Cloud Build → Cloud Run for the study UI + bot, using **GCS volume mounts** for:

- GliNER weights  
- Red-flags knowledge graph **v2**  
- Persistent session JSON (`DIGIMSK_SESSION_STORE_DIR`)

Traditional Chroma RAG is **off** on the hosted bot (`DIGIMSK_RAG=0`); GraphRAG stays on.

## Docs in this folder

| File | Purpose |
|------|---------|
| [STUDY_SERVICE.md](STUDY_SERVICE.md) | Step-by-step: finish and deploy the study Cloud Run service |
| [PLAN.md](PLAN.md) | Architecture, bake vs GCS, ephemeral disk, deploy phases |
| [gcs_layout.md](gcs_layout.md) | Bucket prefixes and env path mapping |
| [.env.cloud.example](.env.cloud.example) | Cloud Run env template |
| [Dockerfile.bot](Dockerfile.bot) | Bot image (no models baked in) |
| [Dockerfile.study](Dockerfile.study) | Study / Reflex image (skeleton) |
| [cloudbuild.yaml](cloudbuild.yaml) | Build images to Artifact Registry |
| [scripts/upload_gcs_assets.ps1](scripts/upload_gcs_assets.ps1) | Upload GliNER + v2 graph; ensure `sessions/` |
| [scripts/deploy_bot.ps1](scripts/deploy_bot.ps1) | Deploy bot with GCS mounts |

## Quick start (ops)

1. Set `DIGIMSK_GCS_BUCKET` (and optional `DIGIMSK_GCP_PROJECT`).  
2. Run `scripts/upload_gcs_assets.ps1` (needs `gcloud` + local GliNER dir).  
3. Build/push via Cloud Build or local Docker.  
4. Run `scripts/deploy_bot.ps1` (mounts bucket at `/mnt/digimsk`; **max-instances=1**).  

Study service deploy and Git “Connect repo” wiring follow once the bot mounts are verified.
