# DigiMSK — Cloud Run + GCS mounts (implementation plan)

**Status:** implementation started (`public_host/cloud_run/`)  
**GCP project:** `YOUR_GCP_PROJECT` (same billing / Vertex as LLM calls)  
**Region:** `us-central1`  
**Storage strategy:** GCS bucket + Cloud Run volume mounts (not bake-into-image for GliNER/graph)

---

## Architecture

```text
Browser
  -> https://digimsk-study-….run.app     (public; later)
       Reflex UI + /_event
       -> httpx + Bearer
  -> digimsk-bot Cloud Run               (authenticated / not public)
       FastAPI :$PORT
       mounts gs://<bucket> -> /mnt/digimsk
         models/gliner/     (read)
         graph/v2/          (read)   <- Graphs/backups/red flags/v2
         sessions/          (read/write)  <- DIGIMSK_SESSION_STORE_DIR
       -> Vertex AI (runtime SA)
```

### Hosted retrieval defaults

| Env | Value | Meaning |
|-----|--------|---------|
| `DIGIMSK_RAG` | `0` | No Chroma / Clinical_sBERT retrieval |
| `DIGIMSK_GRAPH_RAG` | `1` | Local CSV GraphRAG (v2 pack on GCS) |
| `DIGIMSK_GENERATOR_BACKEND` | `vertex` | Same project as today |
| `DIGIMSK_GLINER_MODEL_DIR` | `/mnt/digimsk/models/gliner` | Unchanged GliNER code |
| `DIGIMSK_GRAPH_CSV` | `/mnt/digimsk/graph/v2/red_flags_manual_v2.csv` | From v2 backup |
| `DIGIMSK_GRAPH_INVENTORY` | `/mnt/digimsk/graph/v2/inventory.json` | From v2 backup |
| `DIGIMSK_SESSION_STORE_DIR` | `/mnt/digimsk/sessions` | Durable session JSON |

GliNER / GraphRAG **implementations are unchanged**; only paths and packaging differ.

---

## Why GCS mounts (chosen) vs bake-into-image

| | **Bake models into image** | **GCS + Cloud Run volume mount (chosen)** |
|--|----------------------------|-------------------------------------------|
| Runtime | Self-contained | Paths under `/mnt/digimsk/...` |
| Deploy when code changes | Rebuild/push multi-GB layers | Slim image; fast |
| Update GliNER / graph CSV | New image build | `gsutil` / upload script |
| Artifact Registry cost | Higher (fat images × revisions) | Lower |
| GCS cost | Low | Storage + FUSE ops |
| Cloud Run CPU/RAM | **Same large class** (GliNER + GraphRAG) | **Same** |
| Min instances (warm GliNER) | Same tradeoff | Same tradeoff |
| Ops | Simpler mental model | Bucket IAM + mounts |

**CPU/RAM and min-instances dominate cost either way.** GCS wins for DigiMSK because graph + GliNER change on different cadences than app code, and GraphRAG-only already drops Chroma/sBERT from the hosted footprint.

---

## Ephemeral disk vs session JSON

Bot code already calls `save_session()` → JSON under `DIGIMSK_SESSION_STORE_DIR`. On a lab PC that directory is a normal disk, so logs persist.

On Cloud Run, the container filesystem is **ephemeral**: files disappear when the instance is replaced, scaled to zero, or when traffic hits another instance. Mounting GCS at `DIGIMSK_SESSION_STORE_DIR` makes those writes land in the bucket so study logs survive deploys.

**SQLite checkpoints** (`DIGIMSK_CHECKPOINT_SQLITE`): SQLite-over-GCSFuse is fragile (locking). v1 recommendation: keep checkpoints on local `/tmp` **and** use a single bot instance until a shared checkpointer exists — see open question on max instances below.

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

1. **Done in-repo:** this folder, GCS layout, upload + deploy scripts, bot Dockerfile, GraphRAG-only env template.  
2. **You run:** create bucket, upload assets, build image, `deploy_bot.ps1`.  
3. **Next:** study Dockerfile completion + public service + Connect repo.  
4. **Decide:** max instances for bot given session store (ask below).

---

## Max instances (decided)

**`max-instances=1`** for `digimsk-bot` (v1).

- Session JSON on the shared GCS mount remains durable across deploys.
- LangGraph SQLite stays on `/tmp` on that single instance (avoids split-brain across replicas).
- `deploy_bot.ps1` defaults to `-MaxInstances 1`. Raise only after a shared checkpointer exists.
- Optional later: `-MinInstances 1` to avoid GliNER cold-start latency (cost tradeoff).
