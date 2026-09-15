# TRI-BACK — Cloud Run + GCS mounts (implementation plan)

**Status:** implementation in `public_host/cloud_run/`; cutover runbook is **[STUDY_SERVICE.md](STUDY_SERVICE.md)**  
**GCP project:** `YOUR_GCP_PROJECT` (same billing / Vertex as LLM calls)  
**Region:** `us-central1`  
**Storage strategy:** existing GCS bucket + Cloud Run volume mounts at `/mnt/tri-back` (not bake-into-image for GliNER/graph)

---

## Architecture

```text
Browser
  -> https://tri-back-study-….run.app     (public)
       Reflex UI + /_event
       -> httpx + Bearer
  -> tri-back Cloud Run                  (authenticated / not public)
       FastAPI :$PORT
       mounts gs://<bucket> -> /mnt/tri-back
         models/gliner/     (read)
         graph/v2/          (read)   <- Graphs/backups/red flags/v2
         sessions/          (read/write)  <- TRI_BACK_SESSION_STORE_DIR
       -> Vertex AI (runtime SA)
```

### Hosted retrieval defaults

Prefer `TRI_BACK_*`; legacy `DIGIMSK_*` still resolves.

| Env | Value | Meaning |
|-----|--------|---------|
| `TRI_BACK_RAG` | `0` | No Chroma / Clinical_sBERT retrieval |
| `TRI_BACK_GRAPH_RAG` | `1` | Local CSV GraphRAG (v2 pack on GCS) |
| `TRI_BACK_GENERATOR_BACKEND` | `vertex` | Same project as today |
| `TRI_BACK_GLINER_MODEL_DIR` | `/mnt/tri-back/models/gliner` | Unchanged GliNER code |
| `TRI_BACK_GRAPH_CSV` | `/mnt/tri-back/graph/v2/red_flags_manual_v2.csv` | From v2 backup |
| `TRI_BACK_GRAPH_INVENTORY` | `/mnt/tri-back/graph/v2/inventory.json` | From v2 backup |
| `TRI_BACK_SESSION_STORE_DIR` | `/mnt/tri-back/sessions` | Durable session JSON |

GliNER / GraphRAG **implementations are unchanged**; only paths and packaging differ.

---

## Why GCS mounts (chosen) vs bake-into-image

| | **Bake models into image** | **GCS + Cloud Run volume mount (chosen)** |
|--|----------------------------|-------------------------------------------|
| Runtime | Self-contained | Paths under `/mnt/tri-back/...` |
| Deploy when code changes | Rebuild/push multi-GB layers | Slim image; fast |
| Update GliNER / graph CSV | New image build | `gsutil` / upload script |
| Artifact Registry cost | Higher (fat images × revisions) | Lower |
| GCS cost | Low | Storage + FUSE ops |
| Cloud Run CPU/RAM | **Same large class** (GliNER + GraphRAG) | **Same** |
| Min instances (warm GliNER) | Same tradeoff | Same tradeoff |
| Ops | Simpler mental model | Bucket IAM + mounts |

**CPU/RAM and min-instances dominate cost either way.** GCS wins for TRI-BACK because graph + GliNER change on different cadences than app code, and GraphRAG-only already drops Chroma/sBERT from the hosted footprint.

---

## Ephemeral disk vs session JSON

Bot code already calls `save_session()` → JSON under `TRI_BACK_SESSION_STORE_DIR`. On a lab PC that directory is a normal disk, so logs persist.

On Cloud Run, the container filesystem is **ephemeral**: files disappear when the instance is replaced, scaled to zero, or when traffic hits another instance. Mounting GCS at `TRI_BACK_SESSION_STORE_DIR` makes those writes land in the bucket so study logs survive deploys.

**SQLite checkpoints** (`TRI_BACK_CHECKPOINT_SQLITE`): SQLite-over-GCSFuse is fragile (locking). v1 recommendation: keep checkpoints on local `/tmp` **and** use a single bot instance until a shared checkpointer exists — see open question on max instances below.

---

## Knowledge graph source (v2)

From repo:

- `Graphs/backups/red flags/v2/source/red_flags_manual_v2.csv`  
- `Graphs/backups/red flags/v2/inventory.json`  

Upload script places them at `graph/v2/` in the bucket (see `gcs_layout.md`).

---

## Continuous deploy from Git

Supported: Cloud Build trigger or Cloud Run **Connect repo** with **Dockerfile** (not Buildpacks).  
`cloudbuild.yaml` in this folder builds `Dockerfile.bot` / `Dockerfile.study` into Artifact Registry.  
Volume mounts and secrets are applied at **deploy** time (`deploy_bot.ps1`), not inside the Dockerfile.

---

## Implementation phases

Operator steps are in **[STUDY_SERVICE.md](STUDY_SERVICE.md)** (Phases A–G).

1. **Done in-repo:** monorepo layout, this folder, GCS layout, upload + deploy scripts, bot Dockerfile, GraphRAG-only env template.  
2. **You run next:** Phase A–C (bucket, upload, build bot, `deploy_bot.ps1`, smoke).  
3. **Then:** Phase D–F (Caddy + Reflex in `Dockerfile.study`, public study service, acceptance).  
4. **Optional:** Phase G continuous deploy from Git. **Decided:** bot `max-instances=1` (below).

---

## Max instances (decided)

**`max-instances=1`** for `tri-back` (v1).

- Session JSON on the shared GCS mount remains durable across deploys.
- LangGraph SQLite stays on `/tmp` on that single instance (avoids split-brain across replicas).
- `deploy_bot.ps1` defaults to `-MaxInstances 1`. Raise only after a shared checkpointer exists.
- Optional later: `-MinInstances 1` to avoid GliNER cold-start latency (cost tradeoff).
