"""Enrich manual red-flag ``chunk_string`` values for lexical RAG retrieval.

Prepends pathway-anchored retrieval headers (clinical concept, synonyms, co-occurring
flags) while preserving the original clinical prose at the end. Omits anatomy/location
wording, triage commentary, and graph path metadata from embedded text.
Updates ``Knowledge Base/Red Flags/chunks/manual/red_flags_manual.csv`` in place.

Run from repo root::

    python scripts/enrich_chunks.py
    python scripts/enrich_chunks.py --dry-run
    python scripts/enrich_chunks.py --kb-dir "Knowledge Base/Red Flags"
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Substrings / tokens excluded from synonym lines (generic MSK site boilerplate).
_ANATOMY_PHRASES: frozenset[str] = frozenset(
    {
        "low back",
        "lower back",
        "lumbosacral",
        "thoracolumbar",
        "back pain",
        "spinal pain",
        "thoracolumbar pain",
        "lumbar pain",
        "lumbosacral pain",
    }
)
_ANATOMY_WORDS: frozenset[str] = frozenset(
    {
        "back",
        "lumbar",
        "lumbosacral",
        "thoracolumbar",
        "low",
        "lower",
        "spine",
        "spinal",
        "sacral",
        "sacrum",
        "tailbone",
        "coccyx",
        "cervical",
        "thoracic",
        "vertebral",
    }
)

# Strip location phrases from patient/synonym text (anatomy handled elsewhere).
_LOCATION_STRIP_PATTERNS: tuple[str, ...] = (
    r"\bon\s+(?:my|the|your)\s+(?:low\s+|lower\s+)?back\b",
    r"\b(?:my|the|your)\s+(?:low\s+|lower\s+)?back\b",
    r"\b(?:low|lower)\s+back\b",
    r"\bback\s+pain\b",
    r"\bspinal\s+pain\b",
    r"\blumbosacral\b",
    r"\bthoracolumbar\b",
    r"\blumbar\b",
    r"\binjured\s+my\s+back\b",
    r"\bhit\s+my\s+back\b",
    r"\bbruised\s+my\s+back\b",
    r"\bon\s+(?:my|the)\s+tailbone\b",
    r"\bfell\s+on\s+tailbone\b",
    r"\btailbone(?:\s+injury)?\b",
    r"\bsacral(?:\s+bruising)?\b",
    r"\blanded\s+on\s+my\s+back\b",
)

# Lexical overlap: edge / source_nodes -> extra synonyms and patient phrases.
EDGE_LEXICON: dict[str, dict[str, list[str]]] = {
    "Age over 50": {
        "synonyms": ["over 50", "older than 50", "elderly", "aged 51", "aged 60", "in my fifties"],
        "patient": ["I am over 50", "older adult", "middle-aged and older"],
    },
    "Recent trauma": {
        "synonyms": ["trauma", "recent trauma", "history of trauma", "injury", "fall", "accident", "blunt trauma"],
        "patient": ["after a fall", "fell yesterday", "had an accident", "injured my back", "landed on my back"],
    },
    "Bruising": {
        "synonyms": [
            "bruise",
            "bruising",
            "ecchymosis",
            "abrasion",
            "contusion",
            "skin abrasion",
            "black and blue",
        ],
        "patient": [
            "mild bruising",
            "bruised my back",
            "black and blue on my back",
            "scrape on my back",
            "hit my back",
            "fell on tailbone",
            "landing on hard surface",
            "tailbone injury",
            "sacral bruising",
        ],
    },
    "Female sex": {
        "synonyms": ["female", "woman", "female sex", "biological female"],
        "patient": ["I am a woman", "female patient"],
    },
    "Male sex": {
        "synonyms": ["male", "man", "male sex", "biological male"],
        "patient": ["I am a man", "male patient"],
    },
    "Severe pain": {
        "synonyms": [
            "severe pain",
            "pain 7/10",
            "pain 8/10",
            "pain 9/10",
            "pain 10/10",
            "greater than 7/10",
            "7 out of 10",
            "8 out of 10",
        ],
        "patient": ["worst pain", "severe back pain", "pain is an 8", "10 out of 10 pain"],
    },
    "Corticosteroids": {
        "synonyms": ["steroids", "corticosteroid", "prednisone", "long-term steroids", "steroid therapy"],
        "patient": ["on steroids", "taking prednisone"],
    },
    "Osteoporosis": {
        "synonyms": ["osteoporosis", "osteoporotic", "weak bones", "bone density loss"],
        "patient": ["osteoporosis diagnosis", "fragility fracture risk"],
    },
    "Alcohol": {
        "synonyms": ["alcohol", "alcoholic", "heavy drinking", "excessive alcohol", "alcohol use disorder"],
        "patient": ["I drink heavily", "alcoholic"],
    },
    "Nutrient Deficiency": {
        "synonyms": ["malnutrition", "nutrient deficiency", "poor nutrition", "eating disorder"],
        "patient": ["not eating well", "restricted diet"],
    },
    "Vitamin Deficiency": {
        "synonyms": ["vitamin D deficiency", "low vitamin D", "vitamin deficiency"],
        "patient": ["low vitamin D"],
    },
    "Diabetes": {
        "synonyms": [
            "diabetes",
            "type 2 diabetes",
            "type 1 diabetes",
            "T2DM",
            "diabetic",
            "poorly controlled diabetes",
            "high blood sugar",
        ],
        "patient": ["I have diabetes", "type 2 diabetic", "blood sugar is high", "constantly thirsty"],
    },
    "Rheumatoid arthritis": {
        "synonyms": ["rheumatoid arthritis", "RA", "inflammatory arthritis"],
        "patient": ["rheumatoid arthritis"],
    },
    "Smoking": {
        "synonyms": ["smoking", "smoker", "tobacco", "cigarettes", "heavy smoking"],
        "patient": ["I smoke", "pack a day"],
    },
    "Osteoarthritis": {
        "synonyms": ["osteoarthritis", "OA", "degenerative joint disease"],
        "patient": ["arthritis in my back"],
    },
    "Neuro motor deficit": {
        "synonyms": [
            "leg weakness",
            "foot drop",
            "weak legs",
            "difficulty walking",
            "motor deficit",
            "paralysis",
        ],
        "patient": ["legs feel weak", "trouble walking", "foot drop"],
    },
    "Neuro sensory deficit": {
        "synonyms": [
            "numbness",
            "tingling",
            "pins and needles",
            "sensory loss",
            "electric shock pain",
            "radiculopathy",
        ],
        "patient": ["numbness in leg", "tingling down leg"],
    },
    "Bilat neuro motor deficit": {
        "synonyms": ["bilateral leg weakness", "both legs weak", "bilateral motor deficit"],
        "patient": ["both legs weak"],
    },
    "Bilat neuro sensory deficit": {
        "synonyms": ["bilateral numbness", "both legs numb", "bilateral sensory symptoms"],
        "patient": ["numbness in both legs"],
    },
    "Point tenderness": {
        "synonyms": [
            "point tenderness",
            "tenderness",
            "tender to touch",
            "localized tenderness",
            "spinal tenderness",
            "bone tenderness",
        ],
        "patient": ["very tender over spine", "tenderness at site of fall"],
    },
    "Pain weight-bearing": {
        "synonyms": [
            "pain with standing",
            "pain when walking",
            "weight-bearing pain",
            "worse when standing",
            "pain on standing",
        ],
        "patient": ["hurts when I stand", "pain when walking"],
    },
    "Previous cancer": {
        "synonyms": [
            "history of cancer",
            "prior cancer",
            "cancer survivor",
            "metastatic cancer",
            "malignancy history",
            "breast cancer",
            "prostate cancer",
            "lung cancer",
        ],
        "patient": ["had cancer before", "cancer history"],
    },
    "Unexplained weight loss": {
        "synonyms": ["weight loss", "unintentional weight loss", "losing weight", "cachexia"],
        "patient": ["lost weight without trying", "clothes are looser"],
    },
    "Refractory pain": {
        "synonyms": ["pain not improving", "refractory pain", "failed conservative treatment", "persistent pain"],
        "patient": ["pain not getting better", "physio did not help"],
    },
    "Constant pain": {
        "synonyms": ["constant pain", "unrelenting pain", "pain all the time", "steady worsening pain"],
        "patient": ["pain never stops", "constant ache"],
    },
    "Immunosuppression": {
        "synonyms": ["immunosuppressed", "immunosuppression", "weak immune system", "HIV", "on immunosuppressants"],
        "patient": ["immunosuppressed", "recurrent infections"],
    },
    "Night pain": {
        "synonyms": [
            "night pain",
            "pain at night",
            "wakes at night",
            "second half of the night",
            "cannot get back to sleep",
            "nocturnal pain",
        ],
        "patient": ["pain wakes me at night", "worse at night", "cannot sleep due to pain"],
    },
    "Fever": {
        "synonyms": ["fever", "febrile", "high temperature", "pyrexia", "feeling feverish"],
        "patient": ["I have a fever", "temperature is high"],
    },
    "Chills": {
        "synonyms": ["chills", "rigors", "shivering", "feeling cold"],
        "patient": ["shaking chills"],
    },
    "Night sweats": {
        "synonyms": ["night sweats", "drenching sweats at night", "waking up sweaty"],
        "patient": ["sweating at night"],
    },
    "IV drug user": {
        "synonyms": [
            "IV drug use",
            "intravenous drug use",
            "injection drug use",
            "IVDU",
            "recreational IV drugs",
        ],
        "patient": ["inject drugs", "use needles"],
    },
    "Bladder dysfunction": {
        "synonyms": [
            "urinary retention",
            "incontinence",
            "cannot urinate",
            "bladder dysfunction",
            "cauda equina bladder",
        ],
        "patient": ["cannot pee", "wet myself", "retention of urine"],
    },
    "Bowel dysfunction": {
        "synonyms": [
            "fecal incontinence",
            "bowel incontinence",
            "loss of rectal sensation",
            "constipation with CES",
            "bowel dysfunction",
        ],
        "patient": ["cannot hold stool", "numbness when wiping"],
    },
    "Saddle anaesthesia": {
        "synonyms": [
            "saddle anesthesia",
            "saddle anaesthesia",
            "numbness groin",
            "perineal numbness",
            "genital numbness",
        ],
        "patient": ["numb in groin", "numb buttocks and inner thighs"],
    },
    "Abdominal pain": {
        "synonyms": [
            "abdominal pain",
            "belly pain",
            "stomach pain",
            "pain radiating to back",
            "abdominal pain radiating to back",
            "flank pain",
        ],
        "patient": ["pain in abdomen going to back", "belly pain to back"],
    },
    "Cardiovascular disease": {
        "synonyms": [
            "heart disease",
            "coronary artery disease",
            "peripheral vascular disease",
            "PVD",
            "CAD",
            "vascular disease",
        ],
        "patient": ["heart problems", "blocked arteries"],
    },
    "Hypertension": {
        "synonyms": ["hypertension", "high blood pressure", "HTN", "elevated BP"],
        "patient": ["high blood pressure"],
    },
    "Family history of AAA": {
        "synonyms": ["family history aneurysm", "parent had AAA", "relative with aneurysm"],
        "patient": ["aneurysm runs in family"],
    },
    "Hypercoagulability": {
        "synonyms": ["hypercoagulable", "clotting disorder", "thrombophilia", "DVT risk"],
        "patient": ["blood clots easily"],
    },
    "Venous stasis": {
        "synonyms": ["venous stasis", "immobility", "prolonged sitting", "bed rest", "reduced mobility"],
        "patient": ["not moving much", "stuck in bed"],
    },
    "Endothelial injury": {
        "synonyms": ["venous injury", "surgery trauma to vein", "central line", "recent operation"],
        "patient": ["recent surgery on leg"],
    },
    "Previous DVT": {
        "synonyms": ["prior DVT", "history of DVT", "previous pulmonary embolism", "prior PE", "blood clot before"],
        "patient": ["had a clot before"],
    },
    "Calf redness": {
        "synonyms": ["calf redness", "red calf", "erythema calf", "unilateral calf redness"],
        "patient": ["red swollen calf"],
    },
    "Calf pain": {
        "synonyms": ["calf pain", "leg calf pain", "pain in calf", "unilateral calf pain"],
        "patient": ["my calf hurts"],
    },
    "Calf swelling": {
        "synonyms": ["calf swelling", "swollen calf", "leg swelling", "unilateral leg swelling"],
        "patient": ["calf is swollen"],
    },
    "Recent surgery": {
        "synonyms": ["recent surgery", "post-operative", "after operation", "surgical procedure recent"],
        "patient": ["had surgery last week"],
    },
    "Prolonged bed rest": {
        "synonyms": ["bed rest", "immobilization", "hospital admission immobile", "prolonged immobility"],
        "patient": ["been in bed for days"],
    },
}


def _open_registry_encoding(chunks_csv: Path) -> str:
    from app.services.rag.chunk_and_ingest import _open_registry_encoding as _enc

    return _enc(chunks_csv)


def _extract_original_body(chunk_string: str) -> str:
    """Return clinical prose only (strip a prior enrichment header if present)."""
    text = chunk_string.strip()
    if text.startswith("Red flag "):
        _parts = text.split("\n", 1)
        text = _parts[1].strip() if len(_parts) > 1 else text
    if not text.startswith("Clinical concept:"):
        return text
    if "\n\n" in text:
        body = text.split("\n\n", 1)[1].strip()
        return body or text
    marker = "Co-occurring red flags:"
    if marker in text:
        after = text.split(marker, 1)[1]
        lines = after.split("\n")
        if len(lines) > 1:
            return "\n".join(lines[1:]).strip() or text
    for legacy in ("Related entities for matching:", "Synonyms and patient phrases:"):
        if legacy in text:
            after = text.split(legacy, 1)[1]
            if "\n\n" in after:
                return after.split("\n\n", 1)[1].strip() or text
    return text


def _relation_clause(
    source_nodes: str,
    edge_type: str,
    parent_id: str,
) -> str:
    """Clinical concept line: source node, edge type, pathway only (no path/path_type)."""
    rel = edge_type.strip() or "ASSOCIATED_WITH"
    node = source_nodes.strip() or "red flag"
    pathway = parent_id.strip()
    pathway_suffix = f";{pathway}" if pathway else ""
    return f"{node}; {rel}{pathway_suffix}"


def _concept_description(body: str, edges: str, source_nodes: str) -> str:
    first = body.split(".")[0].strip()
    if len(first) > 20:
        return first[0].lower() + first[1:] if first else first
    node = source_nodes.strip() or edges.strip()
    return node.lower() if node else "red flag finding"


def _lexicon_for(edge_key: str) -> dict[str, list[str]]:
    if edge_key in EDGE_LEXICON:
        return EDGE_LEXICON[edge_key]
    # Fallback: tokenize edge label
    low = edge_key.lower()
    syns = [low]
    if " " in low:
        syns.append(low.replace(" ", ""))
    return {"synonyms": syns, "patient": []}


def _unique_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if not item.strip() or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _is_anatomy_term(text: str) -> bool:
    """True if ``text`` is (or contains) excluded low-back / lumbar site vocabulary."""
    low = text.casefold().strip()
    if not low:
        return True
    if low in _ANATOMY_WORDS:
        return True
    return any(phrase in low for phrase in _ANATOMY_PHRASES)


def _strip_location_from_phrase(phrase: str) -> str:
    """Remove anatomical site wording; keep clinical symptom/finding terms."""
    s = phrase.strip()
    for pattern in _LOCATION_STRIP_PATTERNS:
        s = re.sub(pattern, " ", s, flags=re.IGNORECASE)
    words: list[str] = []
    for word in s.split():
        if word.casefold() in _ANATOMY_WORDS or _is_anatomy_term(word):
            continue
        words.append(word)
    s = " ".join(words)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^(?:on|at|in|to|my|the|your)\s+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(?:on|at|in|to)$", "", s, flags=re.IGNORECASE)
    return s


def _normalize_retrieval_phrase(phrase: str) -> str | None:
    """Site-stripped phrase suitable for synonym lines, or None if empty/anatomy-only."""
    cleaned = _strip_location_from_phrase(phrase)
    if not cleaned or len(cleaned) < 2:
        return None
    if _is_anatomy_term(cleaned):
        return None
    return cleaned


def _synonym_line(concept_key: str, body: str) -> str:
    lex = _lexicon_for(concept_key)
    raw_tokens: list[str] = []
    raw_tokens.extend(lex.get("synonyms", []))
    raw_tokens.extend(lex.get("patient", []))
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "does",
        "not",
        "are",
        "has",
        "when",
        "used",
        "other",
        "alone",
        "guide",
        "triage",
        "urgency",
        "possible",
        "serious",
        "pathology",
        "considered",
        "context",
        "significant",
        "association",
        "reported",
        "combine",
        "determine",
        "flags",
        "red",
    }
    tokens: list[str] = []
    for raw in raw_tokens:
        norm = _normalize_retrieval_phrase(raw)
        if norm:
            tokens.append(norm)
    for word in re.findall(r"[a-zA-Z][a-zA-Z0-9/\-]{2,}", body.lower()):
        if word in stop or _is_anatomy_term(word):
            continue
        norm = _normalize_retrieval_phrase(word)
        if norm:
            tokens.append(norm)
    key_norm = _normalize_retrieval_phrase(concept_key.lower())
    if key_norm and key_norm.casefold() not in {t.casefold() for t in tokens}:
        tokens.insert(0, key_norm)
    merged = _unique_preserve(tokens)
    return ", ".join(merged[:24])


def _cooccurring_line(*, parent_id: str, self_node: str, siblings: list[str]) -> str:
    others = [e for e in siblings if e.casefold() != self_node.casefold()]
    others = others[:10]
    if others:
        return ", ".join(others)
    return f"other {parent_id} pathway red flags"


def enrich_chunk_row(
    row: dict[str, str],
    *,
    siblings_by_parent: dict[str, list[str]],
) -> str:
    body = _extract_original_body(row.get("chunk_string", ""))
    parent_id = row.get("parent_id", "").strip()
    edge_type = row.get("edges", "").strip()
    source_nodes = row.get("source_nodes", "").strip()
    concept_key = source_nodes or edge_type
    relation = _relation_clause(source_nodes, edge_type, parent_id)
    concept = _concept_description(body, source_nodes, edge_type)

    co_line = _cooccurring_line(
        parent_id=parent_id,
        self_node=concept_key,
        siblings=siblings_by_parent.get(parent_id, []),
    )
    header_lines = [
        f"Clinical concept: {concept} ({relation})",
        f"Synonyms and patient phrases: {_synonym_line(concept_key, body)}",
        f"Co-occurring red flags: {co_line}",
    ]
    header_lines.append("")
    header_lines.append(body)
    return "\n".join(header_lines)


def _build_sibling_map(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    by_parent: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        pid = row.get("parent_id", "").strip()
        node = row.get("source_nodes", "").strip()
        if pid and node:
            by_parent[pid].append(node)
    return {k: _unique_preserve(v) for k, v in by_parent.items()}


def enrich_registry_csv(
    chunks_csv: Path,
    *,
    dry_run: bool = False,
    backup: bool = True,
    output_csv: Path | None = None,
) -> tuple[int, int]:
    """Return (rows_updated, rows_skipped)."""
    read_enc = _open_registry_encoding(chunks_csv)
    with chunks_csv.open(newline="", encoding=read_enc) as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [
            {(k or "").strip(): (raw.get(k) or "").strip() for k in fieldnames}
            for raw in reader
        ]

    if not fieldnames or "chunk_string" not in fieldnames:
        raise ValueError(f"Registry missing chunk_string column: {chunks_csv}")

    siblings = _build_sibling_map(rows)
    updated = 0
    skipped = 0

    for row in rows:
        if not row.get("chunk_id") or not row.get("chunk_string"):
            skipped += 1
            continue
        new_text = enrich_chunk_row(row, siblings_by_parent=siblings)
        if new_text == row.get("chunk_string", ""):
            skipped += 1
            continue
        row["chunk_string"] = new_text
        updated += 1

    if dry_run:
        return updated, skipped

    dest = output_csv or chunks_csv
    if backup and dest.resolve() == chunks_csv.resolve():
        bak = chunks_csv.with_suffix(chunks_csv.suffix + ".bak")
        shutil.copy2(chunks_csv, bak)

    write_enc = "utf-8-sig" if read_enc == "utf-8-sig" else "utf-8"
    with dest.open("w", newline="", encoding=write_enc) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    return updated, skipped


def main() -> int:
    from app.services.rag.chunk_and_ingest import default_kb_dir, resolve_manual_chunks_csv

    parser = argparse.ArgumentParser(
        description="Enrich red-flag manual chunk_string values for RAG retrieval.",
    )
    parser.add_argument(
        "--kb-dir",
        type=Path,
        default=None,
        help='Knowledge-base root (default: "Knowledge Base/Red Flags")',
    )
    parser.add_argument(
        "--chunks-csv",
        type=Path,
        default=None,
        help="Override manual registry CSV path",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report counts only")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not write .bak before updating CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write enriched CSV here (default: update --chunks-csv in place)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    log = logging.getLogger(__name__)

    kb_dir = args.kb_dir or default_kb_dir()
    chunks_csv = args.chunks_csv or resolve_manual_chunks_csv(kb_dir)
    if not chunks_csv.is_file():
        log.error("Registry not found: %s", chunks_csv)
        return 1

    updated, skipped = enrich_registry_csv(
        chunks_csv,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        output_csv=args.output,
    )
    log.info(
        "Registry %s: %d enriched, %d unchanged/skipped%s",
        chunks_csv,
        updated,
        skipped,
        " (dry-run)" if args.dry_run else "",
    )
    if args.dry_run:
        read_enc = _open_registry_encoding(chunks_csv)
        with chunks_csv.open(newline="", encoding=read_enc) as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames or [])
            all_rows = [
                {(k or "").strip(): (raw.get(k) or "").strip() for k in fieldnames}
                for raw in reader
            ]
        sib = _build_sibling_map(all_rows)
        for row in all_rows:
            if row.get("chunk_id") == "r_3":
                sample = enrich_chunk_row(row, siblings_by_parent=sib)
                print("--- sample r_3 preview ---\n")
                print(sample)
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
