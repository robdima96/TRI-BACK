# TRI-BACK System Breakdown — 2026.7.15

A **small supervisor pack** for a non-technical audience.

## Deliverables

| Item | Purpose |
|------|---------|
| `01_executive_brief.md` → `pdf/01_executive_brief.pdf` | One-page story |
| `02_file_inventory.md` → `pdf/02_file_inventory.pdf` | Where the main pieces live |
| `diagrams/02_langgraph_pipeline.mmd` | Conversation modes (ask / advise / escalate) |
| `diagrams/03_api_map.mmd` | Local work vs AI wording model |

## Regenerate PDFs

From the repo root:

```powershell
python "Reports/breakdown 2026.7.15/scripts/render_briefing_pdfs.py"
```

Needs TRI-BACK PDF extras (`cd bot && pip install -e ".[pdf]"`).

## Viewing diagrams

Open the `.mmd` files in an editor with Mermaid preview, or paste into [Mermaid Live](https://mermaid.live).

## One sentence

The study website talks to the bot; the bot fills a **checklist**, then either **asks one question** or gives a **recommendation** grounded in local evidence; **Vertex only supplies wording**; study arms only change **what people see**.
