# Chunk registries (review before Chroma ingest)

| Folder | Purpose | Default file | Created by |
|--------|---------|--------------|------------|
| `extracted/` | Auto chunks from PDFs | `red_flags_extracted.csv` | `python scripts/extract_chunks.py` |
| `manual/` | Hand-curated red-flag rows | `red_flags_manual.csv` | You (spreadsheet / editor) |

## Workflow

1. **Auto from PDFs** (optional):  
   `python scripts/extract_chunks.py --kb-dir "Knowledge Base/Red Flags"`  
   → review `extracted/red_flags_extracted.csv`

2. **Manual curation**: edit or create `manual/red_flags_manual.csv`  
   → `python scripts/enrich_chunk_evidence.py` to fill `evidence` / `evidence_level`

3. **Ingest after review** (separate step):  
   `python scripts/ingest_chunks.py --sub-collection red_flags --registry extracted`  
   `python scripts/ingest_chunks.py --sub-collection red_flags --registry manual`

Copy CSVs elsewhere for desktop review; re-ingest from the same path when ready.
