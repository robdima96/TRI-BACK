#!/usr/bin/env python3
"""Promote a red-flags CSV into a versioned Graphs backup and wire the bot.

Typical run (from repo root or Graphs/)::

    python update_graph.py ^
      --csv "bot/Knowledge Base/Red Flags/chunks/manual/red_flags_edges_v4_2026.9.10.csv" ^
      --factors-csv "bot/Knowledge Base/Red Flags/chunks/manual/red_flags_factors_v4_2026.9.10.csv" ^
      --backup-dir "Graphs/backups/red flags/v4"

What it does:
  1. Validate edge CSV shape / graph stats
  2. If a factors CSV is supplied or inferred (``_edges_`` → ``_factors_`` sibling),
     validate it against the inventory and copy it into ``source/`` beside the edges file
  3. Write a v1-shaped backup pack under --backup-dir (source keeps input basenames)
  4. Upsert DIGIMSK_GRAPH_CSV / DIGIMSK_GRAPH_INVENTORY / DIGIMSK_GRAPH_FACTORS in bot/.env
     (paths relative to repo root, pointing at the **Knowledge Base** sources — not Graphs/)
  5. Clear + re-ingest only the chosen Chroma sub-collection (default red_flags)
  6. Optional Neo4j Aura import via Graphs/.env (--neo4j) — edges only
  7. Fast smoke test (local CSV traversal; no GliNER / Vertex)

Use --force if the backup directory already contains files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GRAPHS_DIR = Path(__file__).resolve().parent
REPO_ROOT = GRAPHS_DIR.parent
BOT_DIR = REPO_ROOT / "bot"
BOT_ENV = BOT_DIR / ".env"
V1_BACKUP = GRAPHS_DIR / "backups" / "red flags" / "v1"
DEFAULT_CSV = (
    BOT_DIR
    / "Knowledge Base"
    / "Red Flags"
    / "chunks"
    / "manual"
    / "red_flags_manual_failsafe.csv"
)
DEFAULT_BACKUP = GRAPHS_DIR / "backups" / "red flags" / "v2"

# Ensure Graphs/ and bot/ imports resolve when run from either cwd.
if str(GRAPHS_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPHS_DIR))
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    else:
        path = path.resolve()
    return path


def _backup_nonempty(backup_dir: Path) -> bool:
    if not backup_dir.exists():
        return False
    return any(backup_dir.iterdir())


def _validate_and_stats(csv_path: Path) -> tuple[list[Any], dict[str, Any], str]:
    from graph_builder import load_chunks, sanitize_rel_type

    rows = load_chunks(csv_path)
    if not rows:
        _die(f"No rows parsed from {csv_path}")

    required = (
        "chunk_id",
        "chunk_string",
        "parent_id",
        "source_nodes",
        "edges",
        "path_type",
    )
    # load_chunks already required these via ChunkRow; double-check empties.
    for row in rows:
        if not row.chunk_id or not row.parent_id or not row.source_nodes:
            _die(
                f"Invalid row chunk_id={row.chunk_id!r}: "
                "chunk_id, parent_id, and source_nodes must be non-empty"
            )
        if row.path_type not in {"direct", "mediated", "both"}:
            _die(
                f"Invalid path_type {row.path_type!r} on chunk {row.chunk_id!r} "
                "(expected direct|mediated|both)"
            )

    rel_types = Counter(sanitize_rel_type(r.edges) for r in rows)
    path_types = Counter(r.path_type for r in rows)
    conditions = Counter(r.parent_id for r in rows)
    sources = {r.source_nodes for r in rows}
    mediators = {r.path for r in rows if r.path and r.path != "-"}
    factors = sorted(sources | mediators)
    chunk_ids = sorted({r.chunk_id for r in rows})

    stats = {
        "factors": len(factors),
        "conditions": len(conditions),
        "chunks": len(chunk_ids),
        "relationship_types": dict(rel_types),
        "path_types": dict(path_types),
        "conditions_breakdown": dict(conditions),
    }
    report_lines = [
        f"CSV: {csv_path}",
        f"  rows: {len(rows)}",
        f"  unique Factor names (source_nodes + path): {len(factors)}",
        f"  conditions: {dict(conditions)}",
        f"  relationship types: {dict(rel_types)}",
        f"  path types: {dict(path_types)}",
        f"  chunk ids: {len(chunk_ids)}",
    ]
    return rows, {
        "factors": factors,
        "conditions": sorted(conditions),
        "mediators": sorted(mediators),
        "chunk_ids": chunk_ids,
        "stats": stats,
        "sources": sorted(sources),
    }, "\n".join(report_lines) + "\n"


_FACTOR_SHEET_COLUMNS = (
    "source_nodes",
    "askable",
    "intent",
    "fallback",
    "synonyms",
)


def _infer_factors_csv(edges_path: Path) -> Path | None:
    name = edges_path.name
    if "_edges_" not in name:
        return None
    return edges_path.with_name(name.replace("_edges_", "_factors_", 1))


def _kb_inventory_path(edges_path: Path) -> Path:
    name = edges_path.name
    if "_edges_" in name:
        sibling = name.replace("_edges_", "_inventory_", 1)
        return edges_path.with_name(Path(sibling).stem + ".json")
    return edges_path.with_name(edges_path.stem + "_inventory.json")


def _resolve_factors_csv(edges_path: Path, explicit: str) -> Path | None:
    if (explicit or "").strip():
        path = _resolve_path(explicit)
        if not path.is_file():
            _die(f"Factors CSV not found: {path}")
        return path
    inferred = _infer_factors_csv(edges_path)
    if inferred is None:
        return None
    if not inferred.is_file():
        _die(
            f"Edges CSV {edges_path.name} requires a sibling factors CSV "
            f"at {_rel(inferred)} (or pass --factors-csv)."
        )
    return inferred


def _validate_factors_csv(
    factors_path: Path, inventory_factors: list[str]
) -> tuple[dict[str, Any], str]:
    with factors_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        missing_cols = [c for c in _FACTOR_SHEET_COLUMNS if c not in fieldnames]
        if missing_cols:
            _die(
                f"Factors CSV {factors_path.name} missing columns: {missing_cols}"
            )
        rows = list(reader)

    names: list[str] = []
    seen: set[str] = set()
    dupes: list[str] = []
    askable_yes = 0
    askable_no = 0
    for i, row in enumerate(rows, start=2):
        name = (row.get("source_nodes") or "").strip()
        if not name:
            _die(f"Factors CSV row {i}: empty source_nodes")
        if name in seen:
            dupes.append(name)
        seen.add(name)
        names.append(name)
        askable = (row.get("askable") or "").strip().lower()
        if askable not in {"yes", "no"}:
            _die(
                f"Factors CSV {name!r}: askable must be yes|no, got {askable!r}"
            )
        if askable == "yes":
            askable_yes += 1
            for col in ("intent", "fallback", "synonyms"):
                if not (row.get(col) or "").strip():
                    _die(
                        f"Factors CSV {name!r}: askable=yes requires {col}"
                    )
        else:
            askable_no += 1

    if dupes:
        _die(
            "Factors CSV has duplicate source_nodes: "
            + ", ".join(sorted(set(dupes)))
        )

    inventory_set = set(inventory_factors)
    sheet_set = set(names)
    missing = sorted(inventory_set - sheet_set)
    extra = sorted(sheet_set - inventory_set)
    if missing or extra:
        parts: list[str] = []
        if missing:
            parts.append(f"inventory factors with no sheet row: {missing}")
        if extra:
            parts.append(f"sheet names missing from inventory: {extra}")
        _die("Factors CSV does not match inventory — " + "; ".join(parts))

    meta = {
        "rows": len(names),
        "askable_yes": askable_yes,
        "askable_no": askable_no,
        "source": f"source/{factors_path.name}",
    }
    report = (
        f"Factors CSV: {factors_path}\n"
        f"  rows: {len(names)}\n"
        f"  askable yes/no: {askable_yes}/{askable_no}\n"
        f"  names match inventory ({len(inventory_factors)} factors)\n"
    )
    return meta, report


def _build_inventory(
    *,
    version: str,
    inventory_meta: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).date().isoformat()
    payload = {
        "version": version,
        "exported_on": now,
        "row_count": inventory_meta["stats"]["chunks"],
        "stats": inventory_meta["stats"],
        "factors": inventory_meta["factors"],
        "conditions": inventory_meta["conditions"],
        "mediators": inventory_meta["mediators"],
        "chunk_ids": inventory_meta["chunk_ids"],
    }
    factor_sheet = inventory_meta.get("factor_sheet")
    if factor_sheet:
        payload["factor_sheet"] = factor_sheet
    return payload


def _write_backup_pack(
    *,
    csv_path: Path,
    backup_dir: Path,
    version: str,
    inventory_meta: dict[str, Any],
    validation_report: str,
    factors_path: Path | None = None,
) -> tuple[Path, Path | None]:
    source_dir = backup_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    dest_csv = source_dir / csv_path.name
    shutil.copy2(csv_path, dest_csv)
    dest_factors: Path | None = None
    if factors_path is not None:
        dest_factors = source_dir / factors_path.name
        shutil.copy2(factors_path, dest_factors)

    inventory = _build_inventory(version=version, inventory_meta=inventory_meta)
    inventory_path = backup_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    (backup_dir / "validation_report.txt").write_text(validation_report, encoding="utf-8")

    # Carry forward schema docs from v1 when present (same CSV model).
    for name in ("schema.cypher", "queries.cypher", "graph_model.json"):
        src = V1_BACKUP / name
        if src.is_file():
            shutil.copy2(src, backup_dir / name)

    # Generate Browser import script into the backup pack.
    from export_cypher import build_cypher_file

    import_cypher = build_cypher_file(dest_csv, wipe=True)
    (backup_dir / "import.cypher").write_text(import_cypher, encoding="utf-8")

    source_rel = f"source/{dest_csv.name}"
    factors_rel = f"source/{dest_factors.name}" if dest_factors is not None else None
    files = {
        "source_csv": source_rel,
        "import_cypher": "import.cypher",
        "schema": "schema.cypher",
        "queries": "queries.cypher",
        "graph_model": "graph_model.json",
        "inventory": "inventory.json",
        "validation_report": "validation_report.txt",
    }
    if factors_rel:
        files["factors_csv"] = factors_rel
    contents_rows = [
        f"| `{source_rel}` | Edge table snapshot (same basename as Knowledge Base input) |"
    ]
    if factors_rel:
        contents_rows.append(
            f"| `{factors_rel}` | Factor-node sheet (`askable` / `intent` / `fallback` / `synonyms`) |"
        )
    contents_rows.extend(
        [
            "| `inventory.json` | Factors, conditions, mediators, chunk ids |",
            "| `manifest.json` | Version metadata + stats |",
            "| `import.cypher` | Browser-ready import (schema + wipe + rows) |",
            "| `schema.cypher` / `queries.cypher` / `graph_model.json` | Model docs |",
            "| `validation_report.txt` | Validation output at promote time |",
        ]
    )
    contents_table = "\n".join(contents_rows)
    env_keys = (
        "DIGIMSK_GRAPH_CSV`` / ``DIGIMSK_GRAPH_INVENTORY`` / ``DIGIMSK_GRAPH_FACTORS"
        if factors_rel
        else "DIGIMSK_GRAPH_CSV`` / ``DIGIMSK_GRAPH_INVENTORY"
    )
    promoted_from = csv_path.name
    if factors_path is not None:
        promoted_from = f"{csv_path.name} + {factors_path.name}"
    manifest = {
        "name": "red_flags",
        "version": version,
        "description": (
            f"DigiMSK low-back red flags knowledge graph ({version}) "
            f"promoted from {promoted_from}"
        ),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verified": False,
        "files": files,
        "restore": {
            "python": (
                f'cd Graphs && python import_red_flags.py --csv '
                f'"backups/red flags/{version}/{source_rel}" --wipe'
            ),
            "browser": "Open import.cypher in Neo4j Browser and run",
            "export_cypher_regenerate": (
                f'cd Graphs && python export_cypher.py --csv '
                f'"backups/red flags/{version}/{source_rel}" '
                f'--output "backups/red flags/{version}/import.cypher" --wipe'
            ),
        },
        "stats": inventory_meta["stats"],
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    readme = f"""# Red Flags Knowledge Graph — {version}

Promoted from `{promoted_from}` on {manifest["created_at"]}.

## Contents

| File | Purpose |
|------|---------|
{contents_table}

## Stats

- **{inventory_meta["stats"]["factors"]}** Factor names
- **{inventory_meta["stats"]["conditions"]}** Condition names
- **{inventory_meta["stats"]["chunks"]}** Chunks

## Restore (Neo4j Aura / Desktop)

```powershell
cd Graphs
python import_red_flags.py --csv "backups/red flags/{version}/{source_rel}" --wipe
```

Chatbot GraphRAG reads the Knowledge Base CSVs via ``{env_keys}`` in ``bot/.env``. This Graphs pack is a local backup (gitignored); do not point the bot at it.
"""
    (backup_dir / "README.md").write_text(readme, encoding="utf-8")
    return dest_csv, dest_factors


def _upsert_bot_env(
    csv_source: Path,
    inventory_source: Path,
    factors_source: Path | None = None,
) -> None:
    updates = {
        "DIGIMSK_GRAPH_CSV": _rel(csv_source),
        "DIGIMSK_GRAPH_INVENTORY": _rel(inventory_source),
    }
    if factors_source is not None:
        updates["DIGIMSK_GRAPH_FACTORS"] = _rel(factors_source)
    existing = ""
    if BOT_ENV.is_file():
        existing = BOT_ENV.read_text(encoding="utf-8")

    lines = existing.splitlines()
    keys_done: set[str] = set()
    out: list[str] = []
    skip_next_blank_after_dup_comment = False
    for line in lines:
        stripped = line.strip()
        if stripped == "# Red-flags graph pack (local GraphRAG / agentic ontology)":
            if "DIGIMSK_GRAPH_CSV" in keys_done or any(
                existing_line.strip().startswith("DIGIMSK_GRAPH_CSV=")
                for existing_line in out
            ):
                skip_next_blank_after_dup_comment = True
                continue
        if skip_next_blank_after_dup_comment and not stripped:
            skip_next_blank_after_dup_comment = False
            continue
        skip_next_blank_after_dup_comment = False
        matched = False
        for key, value in updates.items():
            if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
                out.append(f"{key}={value}")
                keys_done.add(key)
                matched = True
                break
        if not matched:
            out.append(line)

    if keys_done != set(updates):
        if out and out[-1].strip():
            out.append("")
        if "DIGIMSK_GRAPH_CSV" not in keys_done:
            out.append("# Red-flags graph pack (local GraphRAG / agentic ontology)")
        for key, value in updates.items():
            if key not in keys_done:
                out.append(f"{key}={value}")

    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    BOT_ENV.parent.mkdir(parents=True, exist_ok=True)
    BOT_ENV.write_text(text, encoding="utf-8")
    print(f"Updated { _rel(BOT_ENV) }:")
    for key, value in updates.items():
        print(f"  {key}={value}")


def _reingest_chroma(csv_path: Path, sub_collection: str) -> None:
    from app.services.rag.chunk_and_ingest import ingest_chunks_from_csv
    from app.services.rag.store import clear_sub_collection_documents, validate_sub_collection

    canonical = validate_sub_collection(sub_collection)
    print(f"Chroma: clearing sub-collection {canonical!r} only ...")
    removed = clear_sub_collection_documents(canonical)
    print(f"  removed {removed} document(s)")
    print(f"Chroma: ingesting {csv_path.name} -> {canonical!r} ...")
    code = ingest_chunks_from_csv(
        sub_collection=canonical,
        chunks_csv=csv_path,
        registry_format="auto",
    )
    if code != 0:
        _die(f"Chroma ingest failed with exit code {code}")
    print("  ingest OK")


def _neo4j_import(csv_backup: Path) -> None:
    from import_red_flags import import_csv
    from neo4j_client import Neo4jConfig

    config = Neo4jConfig.from_env()
    print(f"Neo4j: importing into {config.uri} (wipe=True) ...")
    stats = import_csv(csv_backup, config, wipe=True)
    print(f"  Neo4j import OK: {stats}")


def _alias_targets() -> set[str]:
    from app.services.rag import factor_patterns as fp

    targets = set(fp._KIND_LABEL_FACTORS.values())
    targets.update(fp._TEXT_ALIASES.values())
    targets.update({"Age over 50", "Severe pain", "Male sex", "Female sex"})
    return targets


def _warn_factor_aliases(
    factors: list[str],
    *,
    previous_factors: set[str] | None,
) -> None:
    targets = _alias_targets()
    new_factors = sorted(set(factors) - (previous_factors or set()))
    no_shortcut = sorted(f for f in factors if f not in targets)

    print("\nFactor matching notes:")
    if new_factors:
        print(f"  New factors vs previous inventory ({len(new_factors)}):")
        for name in new_factors[:40]:
            print(f"    + {name}")
        if len(new_factors) > 40:
            print(f"    ... and {len(new_factors) - 40} more")
    else:
        print("  No new factor names vs previous inventory.")

    print(
        f"  Factors without dedicated alias/kind shortcut "
        f"(exact-name regex only): {len(no_shortcut)}"
    )
    # Prefer highlighting the new ones that lack shortcuts.
    highlight = [f for f in new_factors if f not in targets] or no_shortcut[:15]
    for name in highlight[:25]:
        print(f"    - {name}")
    if len(highlight) > 25:
        print(f"    ... and {len(highlight) - 25} more")
    print(
        "  Edit bot/app/services/rag/factor_patterns.py if everyday synonyms "
        "should map to these names."
    )


def _load_previous_factors(backup_dir: Path) -> set[str]:
    candidates = [backup_dir / "inventory.json"]
    parent = backup_dir.parent
    if parent.is_dir():
        siblings = sorted(
            (
                path
                for path in parent.iterdir()
                if path.is_dir() and path != backup_dir
            ),
            key=lambda path: path.name,
        )
        for sibling in reversed(siblings):
            inventory = sibling / "inventory.json"
            if inventory.is_file():
                candidates.append(inventory)
                break
    candidates.append(V1_BACKUP / "inventory.json")
    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                return set(data.get("factors") or [])
            except (OSError, json.JSONDecodeError):
                continue
    return set()


def _smoke_local(csv_backup: Path, factors: list[str]) -> None:
    from app.schemas import ChecklistItem
    from app.services.graphrag.local_graph import LocalGraphClient, reset_graph_client_cache
    from app.services.graphrag.orchestrator import traverse_from_turn

    reset_graph_client_cache()
    client = LocalGraphClient(csv_path=csv_backup)
    probe = [f for f in ("Recent trauma", "Severe pain", "Age over 50") if f in factors]
    if not probe:
        probe = factors[:3]
    if not probe:
        _die("Smoke test: no factors available")

    segments = client.paths_for_factors(probe)
    print(f"\nSmoke (local): paths_for_factors({probe!r}) -> {len(segments)} segment(s)")
    if not segments:
        _die("Smoke test failed: no path segments for probe factors")

    checklist = [
        ChecklistItem(
            text=probe[0],
            kind="symptom",
            source="pattern",
            label="symptom",
        )
    ]
    if "Age over 50" in factors:
        checklist.append(
            ChecklistItem(text="70", kind="demographic", source="pattern", label="age")
        )
    if "Severe pain" in factors:
        checklist.append(
            ChecklistItem(
                text="severe pain",
                kind="severity",
                source="pattern",
                label="symptom_severity",
            )
        )

    trace = traverse_from_turn(
        checklist=checklist,
        chunk_matches=None,
        title="update_graph smoke",
        graph_client=client,
    )
    print(
        f"  traverse_from_turn: matched={trace.matched_factors} "
        f"conditions={trace.candidate_conditions[:5]} "
        f"nodes={len(trace.nodes)} edges={len(trace.edges)}"
    )
    if not trace.matched_factors and not trace.nodes:
        _die("Smoke test failed: empty traversal")
    print("  smoke OK")
    reset_graph_client_cache()


def _infer_version(backup_dir: Path) -> str:
    name = backup_dir.name.strip()
    if re.fullmatch(r"v\d+", name, flags=re.IGNORECASE):
        return name.lower()
    return name or "v_next"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote a red-flags CSV into a Graphs backup and wire DigiMSK bot."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=str(DEFAULT_CSV.relative_to(REPO_ROOT)),
        help="Source edge CSV (Knowledge Base manual registry or other path)",
    )
    parser.add_argument(
        "--factors-csv",
        type=str,
        default="",
        help=(
            "Factor-node sheet CSV (askable/intent/fallback/synonyms). "
            "If omitted, inferred as a sibling replacing _edges_ with _factors_."
        ),
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        default=str(DEFAULT_BACKUP.relative_to(REPO_ROOT)),
        help="Backup pack directory (e.g. Graphs/backups/red flags/v2)",
    )
    parser.add_argument(
        "--chroma-collection",
        type=str,
        default="red_flags",
        help="Chroma sub-collection to clear+reingest (default: red_flags)",
    )
    parser.add_argument(
        "--skip-chroma",
        action="store_true",
        help="Skip Chroma clear/ingest (not recommended)",
    )
    parser.add_argument(
        "--neo4j",
        action="store_true",
        help="Import into Neo4j Aura/Desktop using Graphs/.env (wipe=True)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into a non-empty backup directory",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip local traversal smoke test",
    )
    args = parser.parse_args(argv)

    csv_path = _resolve_path(args.csv)
    backup_dir = _resolve_path(args.backup_dir)
    version = _infer_version(backup_dir)

    if not csv_path.is_file():
        _die(f"Source CSV not found: {csv_path}")
    factors_path = _resolve_factors_csv(csv_path, args.factors_csv)

    if _backup_nonempty(backup_dir) and not args.force:
        _die(
            f"Backup directory is not empty: {backup_dir}\n"
            "  Re-run with --force to overwrite, or choose an empty path."
        )

    print(f"Source CSV:   {csv_path}")
    print(f"Factors CSV:  {factors_path if factors_path else '(none)'}")
    print(f"Backup dir:   {backup_dir} (version={version})")
    print(f"Chroma:       {args.chroma_collection} (skip={args.skip_chroma})")
    print(f"Neo4j import: {args.neo4j}")

    previous_factors = _load_previous_factors(backup_dir)
    rows, inventory_meta, report = _validate_and_stats(csv_path)
    if factors_path is not None:
        factor_meta, factor_report = _validate_factors_csv(
            factors_path, inventory_meta["factors"]
        )
        inventory_meta["factor_sheet"] = factor_meta
        report = report + factor_report
    print("\nValidation:")
    print(report.rstrip())

    backup_dir.mkdir(parents=True, exist_ok=True)
    dest_csv, dest_factors = _write_backup_pack(
        csv_path=csv_path,
        backup_dir=backup_dir,
        version=version,
        inventory_meta=inventory_meta,
        validation_report=report,
        factors_path=factors_path,
    )
    inventory_path = backup_dir / "inventory.json"
    kb_inventory = _kb_inventory_path(csv_path)
    kb_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    if factors_path is not None and isinstance(kb_payload.get("factor_sheet"), dict):
        kb_payload["factor_sheet"]["source"] = factors_path.name
    kb_inventory.write_text(
        json.dumps(kb_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\nBackup pack written ({len(rows)} rows).")
    print(f"  CSV copy:    {_rel(dest_csv)}")
    if dest_factors is not None:
        print(f"  Factors:     {_rel(dest_factors)}")
    print(f"  Inventory:   {_rel(inventory_path)}")
    print(f"  KB inventory:{_rel(kb_inventory)}")

    _upsert_bot_env(csv_path, kb_inventory, factors_path)

    if not args.skip_chroma:
        try:
            _reingest_chroma(csv_path, args.chroma_collection)
        except Exception as exc:
            _die(
                f"Chroma step failed: {exc}\n"
                "  Tip: stop uvicorn/bot if Chroma reports SQLITE_BUSY; "
                "ensure DIGIMSK_ENCODER_DIR (Clinical_sBERT) is configured."
            )
    else:
        print("Chroma: skipped (--skip-chroma)")

    if args.neo4j:
        try:
            _neo4j_import(dest_csv)
        except Exception as exc:
            _die(f"Neo4j import failed: {exc}")
    else:
        print("Neo4j: skipped (pass --neo4j to import into Aura using Graphs/.env)")

    _warn_factor_aliases(
        inventory_meta["factors"],
        previous_factors=previous_factors,
    )

    if not args.skip_smoke:
        _smoke_local(dest_csv, inventory_meta["factors"])
    else:
        print("Smoke: skipped")

    print(
        "\nDone. Restart the DigiMSK bot (uvicorn) so LocalGraphClient / "
        "factor-pattern caches reload DIGIMSK_GRAPH_CSV + DIGIMSK_GRAPH_INVENTORY"
        " + DIGIMSK_GRAPH_FACTORS."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
