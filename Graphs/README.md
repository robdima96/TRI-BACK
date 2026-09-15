# TRI-BACK Red Flags Knowledge Graph (Neo4j)

Import the formatted red-flags CSV into Neo4j and explore it in Browser, Bloom, or an exported HTML graph. The graph is structured for later LLM navigation during screening → discrimination → disposition.

## Graph model

| Node label | Source | Role |
|------------|--------|------|
| `Factor` | `source_nodes`, `path` | Symptoms, traits, and mediating concepts (e.g. Osteoporosis) |
| `Condition` | `parent_id` | Red-flag diagnoses (Fracture, Malignancy, CES, …) |
| `Chunk` | each CSV row | Evidence text, citations, discriminator flags |

| Relationship | Meaning |
|--------------|---------|
| `RISK_FACTOR_FOR`, `SUGGESTIVE_OF`, … | From `edges` column — factor → condition (direct) or factor → mediator |
| `CONTRIBUTES_TO` | Mediated path: mediator factor → condition |
| `DESCRIBES` / `APPLIES_TO` | Chunk links to factor and condition |

**Path mediators:** When `path_type` is `mediated` or `both`, the `path` value is merged as a `Factor` node — the same label as `source_nodes`. A concept can be a source in one row and a mediator in another (e.g. Osteoporosis). The chain is `source_nodes` → `path` → `parent_id`.

**Path types**

- `direct` — factor connects straight to condition
- `mediated` — factor → mediator (`path`) → condition via `CONTRIBUTES_TO`
- `both` — direct and mediated edges are created

## Connect to Neo4j (you choose how)

### Step 1 — Configure connection

Interactive wizard (writes `Graphs/.env` and tests the connection):

```powershell
python setup_connection.py
```

Or test / set credentials without prompts:

```powershell
python setup_connection.py --test
python setup_connection.py --write --uri "neo4j+s://YOUR_ID.databases.neo4j.io" --username neo4j --password "YOUR_PASSWORD" --database neo4j
```

Get URI and credentials from [Neo4j Aura Console](https://console.neo4j.io) → your instance → **Connect**.

`NEO4J_DATABASE` can be left blank — the pipeline auto-fills it from your Aura instance id (the id in the URI hostname, e.g. `bb1ec188`). Use `neo4j` for Neo4j Desktop.

### Step 2 — Load data (pick one path)

**A. Python import** (uses `Graphs/.env`):

```powershell
python import_red_flags.py --test
python import_red_flags.py --wipe
```

CLI overrides if you prefer not to edit `.env`:

```powershell
python import_red_flags.py --uri "neo4j+s://..." --username neo4j --password "..." --wipe
```

**B. Manual Browser import** (no Python driver needed — paste into Neo4j Browser):

```powershell
python export_cypher.py --wipe
```

Then open `output/red_flags_import.cypher` in Neo4j Browser and run it.

## Setup

```powershell
cd Graphs
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python setup_connection.py
```

## Import (after connection is configured)

Validate CSV parsing first (no database required):

```powershell
python validate_csv.py
```

## View and navigate

### Neo4j Browser (recommended)

1. Open [Neo4j Aura Console](https://console.neo4j.io)
2. Connect to your instance → **Explore** / Browser
3. Run queries from `queries.cypher`

Example — all conditions and linked factors:

```cypher
MATCH (f:Factor)-[r]->(c:Condition)
RETURN c, r, f;
```

### Interactive HTML export

```powershell
python visualize.py
python visualize.py --condition Fracture
start output\red_flags_graph.html
```

### Python API (for LLM integration)

```python
from navigate import RedFlagsGraph

with RedFlagsGraph() as g:
    hits = g.conditions_for_factors(["Fever", "IV drug user"])
    discs = g.discriminators_for_conditions(["Infection", "Malignancy"])
    evidence = g.evidence_for_link("Fever", "Infection")
```

`conditions_for_factors` supports the screening phase; `discriminators_for_conditions` supports discrimination when multiple `parent_id` values match.

## Files

| File | Purpose |
|------|---------|
| `setup_connection.py` | Configure and test Neo4j connection |
| `export_cypher.py` | Export `.cypher` file for manual Browser import |
| `import_red_flags.py` | CSV → Neo4j import CLI |
| `neo4j_client.py` | Shared connection config + test |
| `graph_builder.py` | Schema + Cypher generation |
| `navigate.py` | Traversal helpers for agents |
| `visualize.py` | PyVis HTML export |
| `queries.cypher` | Starter Browser queries |
| `config.py` | Paths and env loading |

## Next steps (LLM)

- Call `RedFlagsGraph.conditions_for_factors()` with encoder-extracted symptoms
- When multiple conditions match, call `discriminators_for_conditions()`
- Fetch `evidence_for_link()` for cited responses
- Optionally expose `navigate.py` methods as MCP or REST tools for your bot

## Web graph explorer

Interactive password-protected browser UI in `Graphs/app/` (Cytoscape.js + neo4j-driver). See `Graphs/app/README.md`.
