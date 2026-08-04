# GCS bucket layout for DigiMSK Cloud Run

Default bucket name (override with `DIGIMSK_GCS_BUCKET`):

```text
digimsk-cloudrun-<PROJECT_ID>
```

Example: `digimsk-cloudrun-YOUR_GCP_PROJECT`

Cloud Run mounts the **entire bucket** at:

```text
/mnt/digimsk
```

(`readonly=false` so `sessions/` is writable; model/graph trees should be treated as read-mostly.)

## Prefixes

```text
gs://<bucket>/
  models/
    gliner/                 # full GliNER-BioMed tree (config, weights, …)
  graph/
    v2/
      red_flags_manual_v2.csv   # from Graphs/backups/red flags/v2/source/
      inventory.json            # from Graphs/backups/red flags/v2/
  sessions/                 # bot DIGIMSK_SESSION_STORE_DIR (JSON per session)
  checkpoints/              # optional; prefer local /tmp until SQLite-on-FUSE is validated
```

## Env mapping (bot service)

| Env var | Container path |
|---------|----------------|
| `DIGIMSK_GLINER_MODEL_DIR` | `/mnt/digimsk/models/gliner` |
| `DIGIMSK_GRAPH_CSV` | `/mnt/digimsk/graph/v2/red_flags_manual_v2.csv` |
| `DIGIMSK_GRAPH_INVENTORY` | `/mnt/digimsk/graph/v2/inventory.json` |
| `DIGIMSK_SESSION_STORE_DIR` | `/mnt/digimsk/sessions` |
| `DIGIMSK_CHECKPOINT_SQLITE` | `/tmp/langgraph_checkpoints.sqlite` (v1 default; requires **max-instances=1**) |

## IAM

Cloud Run runtime service account needs on the bucket:

- `roles/storage.objectViewer` on `models/**` and `graph/**` (or whole bucket)
- `roles/storage.objectUser` (or Admin) on `sessions/**` for create/update

Also: `roles/aiplatform.user` for Vertex in the same project.
