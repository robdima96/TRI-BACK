# GCS bucket layout for TRI-BACK Cloud Run

The **bucket name cannot be renamed**. Keep:

```text
digimsk-cloudrun-<PROJECT_ID>
```

Example: `digimsk-cloudrun-YOUR_GCP_PROJECT`

Override with `TRI_BACK_GCS_BUCKET`.

Services mount the **entire bucket** at:

```text
/mnt/tri-back
```

(`readonly=false` so `sessions/` is writable; model/graph trees should be treated as read-mostly.)

## Prefixes

```text
gs://<bucket>/
  models/
    gliner/                 # full GliNER-BioMed tree (config, weights, …)
  graph/
    v4/
      red_flags_edges_v4_2026.9.10.csv
      red_flags_factors_v4_2026.9.10.csv
      red_flags_inventory_v4_2026.9.10.json
    v2/                     # leftover from earlier deploys; not used by tri-back
  sessions/                 # bot TRI_BACK_SESSION_STORE_DIR + study sessions dir
  study/
    tri_back.db              # study SQLite
  checkpoints/              # optional; prefer local /tmp until SQLite-on-FUSE is validated
```

## Env mapping (bot service)

| Env var | Container path |
|---------|----------------|
| `TRI_BACK_GLINER_MODEL_DIR` | `/mnt/tri-back/models/gliner` |
| `TRI_BACK_GRAPH_CSV` | `/mnt/tri-back/graph/v4/red_flags_edges_v4_2026.9.10.csv` |
| `TRI_BACK_GRAPH_FACTORS` | `/mnt/tri-back/graph/v4/red_flags_factors_v4_2026.9.10.csv` |
| `TRI_BACK_GRAPH_INVENTORY` | `/mnt/tri-back/graph/v4/red_flags_inventory_v4_2026.9.10.json` |
| `TRI_BACK_SESSION_STORE_DIR` | `/mnt/tri-back/sessions` |
| `TRI_BACK_CHECKPOINT_SQLITE` | `/tmp/langgraph_checkpoints.sqlite` (v1 default; requires **max-instances=1**) |

## IAM

Cloud Run runtime service account needs on the bucket:

- `roles/storage.objectViewer` on `models/**` and `graph/**` (or whole bucket)
- `roles/storage.objectUser` (or Admin) on `sessions/**` for create/update

Also: `roles/aiplatform.user` for Vertex in the same project.
