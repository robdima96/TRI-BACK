# Red Flags Knowledge Graph — v1

Validated backup of the DigiMSK low-back red flags Neo4j configuration.

## Contents

| File | Purpose |
|------|---------|
| `manifest.json` | Version metadata, stats, restore commands |
| `graph_model.json` | Machine-readable schema (nodes, relationships, CSV mapping) |
| `inventory.json` | Full list of factors, conditions, mediators, chunk ids |
| `source/red_flags_manual_failsafe.csv` | Source data snapshot |
| `import.cypher` | Complete Browser-ready import (schema + 66 rows + verify) |
| `schema.cypher` | Constraints and model documentation |
| `queries.cypher` | Exploration queries |
| `validation_report.txt` | Output of `validate_csv.py` at backup time |

## Graph summary (v1)

- **48** Factor nodes
- **6** Condition nodes (Fracture, Malignancy, Infection, CES, AAA, DVT)
- **66** Chunk nodes
- Path types: direct (49), mediated (14), both (3)

## Restore

### Python import

```powershell
cd Graphs
python import_red_flags.py --csv "backups/red flags/v1/source/red_flags_manual_failsafe.csv" --wipe
```

### Neo4j Browser (manual)

1. Open your Aura / Desktop instance in Browser
2. Run `import.cypher` (paste full file or section-by-section)

### Regenerate `import.cypher` from source

```powershell
cd Graphs
python export_cypher.py --csv "backups/red flags/v1/source/red_flags_manual_failsafe.csv" --output "backups/red flags/v1/import.cypher" --wipe
```

## Model reference

See `graph_model.json` for the canonical mapping from CSV columns to graph elements. Key decisions in v1:

- `Factor` label used for both `source_nodes` and `path` mediators
- `loc` stored on Chunk only (no BodyLocation nodes)
- Mediated chains: `source -[edges]-> mediator -[CONTRIBUTES_TO]-> condition`
