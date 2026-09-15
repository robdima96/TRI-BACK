# Red Flags Knowledge Graph — v3

Promoted from `red_flags_manual_v3_2026.9.9.csv` on 2026-09-10T17:54:04Z.

## Contents

| File | Purpose |
|------|---------|
| `source/red_flags_manual_v3_2026.9.9.csv` | Source data snapshot (same basename as Knowledge Base input) |
| `inventory.json` | Factors, conditions, mediators, chunk ids |
| `manifest.json` | Version metadata + stats |
| `import.cypher` | Browser-ready import (schema + wipe + rows) |
| `schema.cypher` / `queries.cypher` / `graph_model.json` | Model docs |
| `validation_report.txt` | Validation output at promote time |

## Stats

- **58** Factor names
- **7** Condition names
- **86** Chunks

## Restore (Neo4j Aura / Desktop)

```powershell
cd Graphs
python import_red_flags.py --csv "backups/red flags/v3/source/red_flags_manual_v3_2026.9.9.csv" --wipe
```

Chatbot GraphRAG reads this pack via ``TRI_BACK_GRAPH_CSV`` / ``TRI_BACK_GRAPH_INVENTORY`` in ``bot/.env`` (local CSV; Neo4j optional).
