# Red Flags Knowledge Graph — v2

Promoted from `red_flags_manual_v2.csv` on 2026-07-22T17:18:15Z.

## Contents

| File | Purpose |
|------|---------|
| `source/red_flags_manual_v2.csv` | Source data snapshot (same basename as Knowledge Base input) |
| `inventory.json` | Factors, conditions, mediators, chunk ids |
| `manifest.json` | Version metadata + stats |
| `import.cypher` | Browser-ready import (schema + wipe + rows) |
| `schema.cypher` / `queries.cypher` / `graph_model.json` | Model docs |
| `validation_report.txt` | Validation output at promote time |

## Stats

- **59** Factor names
- **7** Condition names
- **79** Chunks

## Restore (Neo4j Aura / Desktop)

```powershell
cd Graphs
python import_red_flags.py --csv "backups/red flags/v2/source/red_flags_manual_v2.csv" --wipe
```

Chatbot GraphRAG reads this pack via ``TRI_BACK_GRAPH_CSV`` / ``TRI_BACK_GRAPH_INVENTORY`` in ``bot/.env`` (local CSV; Neo4j optional).
