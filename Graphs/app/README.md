# TRI-BACK Red Flags Graph Explorer

Password-protected web app for interactively exploring the red flags Neo4j knowledge graph (v1). Built with **Express**, the official **neo4j-driver**, and **Cytoscape.js**.

## Features

- Full graph view with zoom, pan, and fit-to-screen
- Filter by node type (`Factor`, `Condition`, `Chunk`)
- Filter by relationship type (`APPLIES_TO`, `RISK_FACTOR_FOR`, etc.)
- Focus on a specific node (2-hop neighborhood)
- Click nodes/edges to inspect properties
- Blue & white UI

## Setup

```powershell
cd Graphs/app
copy .env.example .env
# Edit .env — set APP_PASSWORD and SESSION_SECRET
# Neo4j credentials are read from Graphs/.env
npm install
npm start
```

Open: **http://localhost:3847**

Set `APP_PASSWORD` in `Graphs/app/.env` (required; `.env.example` uses `change-me`).

## Configuration

| Variable | Location | Purpose |
|----------|----------|---------|
| `APP_PASSWORD` | `Graphs/app/.env` | Login password for the web UI |
| `SESSION_SECRET` | `Graphs/app/.env` | Session cookie signing |
| `PORT` | `Graphs/app/.env` | Server port (default 3847) |
| `NEO4J_*` | `Graphs/.env` | Aura connection (shared with import pipeline) |

## Public web link (password-protected)

### Option A — Cloudflare Tunnel (free, dedicated URL)

```powershell
# Install cloudflared, then:
cloudflared tunnel --url http://localhost:3847
```

Share the generated `*.trycloudflare.com` URL. Users enter `APP_PASSWORD` on the login page.

### Option B — ngrok

```powershell
ngrok http 3847
```

### Option C — Deploy to Render / Railway

1. Set root directory to `Graphs/app`
2. Build: `npm install`
3. Start: `npm start`
4. Add env vars: `APP_PASSWORD`, `SESSION_SECRET`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`

## API (authenticated)

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/login` | `{ "password": "..." }` |
| `GET /api/graph` | `?labels=Factor,Condition&relTypes=DESCRIBES,APPLIES_TO&focusNodeId=...` |
| `GET /api/metadata` | Available labels, relationship types, node list |
| `GET /api/health` | Neo4j connectivity check |

## Project layout

```
Graphs/app/
  server.js           Express server + auth
  lib/
    config.js         Env loading (app + Graphs/.env)
    neo4j.js          neo4j-driver connection
    graphApi.js       Cypher queries → JSON for Cytoscape
  public/
    index.html        Graph explorer
    login.html        Password gate
    css/styles.css
    js/tri_back_cytoscape.js  Shared Cytoscape kernel
    js/graph.js       Cytoscape rendering + filters
    js/login.js
```

## Graph source

Connects to the live Aura database populated from:

`Graphs/backups/red flags/v1/`

Restore if needed:

```powershell
cd Graphs
python import_red_flags.py --csv "backups/red flags/v1/source/red_flags_manual_failsafe.csv" --wipe
```
