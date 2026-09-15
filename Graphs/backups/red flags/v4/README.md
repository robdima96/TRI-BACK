# Red Flags Knowledge Graph — v4

Promoted from `red_flags_edges_v4_2026.9.10.csv + red_flags_factors_v4_2026.9.10.csv` on 2026-09-10T20:58:44Z.

## Contents

| File | Purpose |
|------|---------|
| `source/red_flags_edges_v4_2026.9.10.csv` | Edge table snapshot (same basename as Knowledge Base input) |
| `source/red_flags_factors_v4_2026.9.10.csv` | Factor-node sheet (`askable` / `intent` / `fallback` / `synonyms`) |
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
python import_red_flags.py --csv "backups/red flags/v4/source/red_flags_edges_v4_2026.9.10.csv" --wipe
```

Chatbot GraphRAG reads this pack via ``TRI_BACK_GRAPH_CSV`` / ``TRI_BACK_GRAPH_INVENTORY`` / ``TRI_BACK_GRAPH_FACTORS`` in ``bot/.env`` (local CSV; Neo4j optional). The factors sheet is node metadata for intake and is **not** imported as extra Neo4j relationships.
