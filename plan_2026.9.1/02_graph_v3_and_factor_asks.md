# Phase 2 — Graph ingest and factor-question plumbing

**Status:** not started · **Prerequisite:** [Phase 1](01_factor_state_and_denials.md) merged · **Unblocks:** [Phase 3](03_relevance_ranker.md)
**Parent design:** [graph_driven_intake.md](graph_driven_intake.md)

---

## Why this is its own phase

Phase 3 is the behaviour change. This phase makes that change *possible* without making it yet, so the two can be reviewed separately.

Two independent things have to exist before a ranker can pick a factor question:

(1) neighbourhood from all factor–condition edges, with CONFIRM_AGAINST included for eligibility and excluded from risk/escalation
(2) orchestrator plumbing so a non-slot factor ask can be asked and credited. 

Item 1 is graph ingest hygiene plus a richer ranking input; item 2 is the hard blocker.

At the end of this phase the bot still asks the same questions in the same order. A factor ask is reachable only through a test hook.

## Scope

In: `CONFIRM_AGAINST` scoring exclusion, load the already-promoted v4 factors CSV (`askable` / `intent` / `fallback` / `synonyms`) into `csv_rows` / `ontology.py`, `is_specific` exposure, `asked_factor` plumbing, factor-answer crediting.

Out: neighbourhood, ranking, relaxed slot order, escalation, arm 3. Authoring and promoting the v4 pack is done (see §1 / §7).

---

## Part A — Graph v4 scoring and factor-sheet loaders

### 1. Point the bot at v4 — already done

Not remaining work. The v4 tables are authored, a local Graphs backup pack exists, Aura was wiped and reloaded from the edges CSV, and the bot reads the Knowledge Base files (not `Graphs/`):

- `bot/Knowledge Base/Red Flags/chunks/manual/red_flags_edges_v4_2026.9.10.csv` is the edge table (v3 relationship rows, unchanged columns)
- `bot/Knowledge Base/Red Flags/chunks/manual/red_flags_factors_v4_2026.9.10.csv` is the factor-node sheet (58 rows; `askable` / `intent` / `fallback` / `synonyms`)
- `bot/Knowledge Base/Red Flags/chunks/manual/red_flags_inventory_v4_2026.9.10.json` is the factor/condition inventory
- `bot/.env` has `TRI_BACK_GRAPH_CSV` / `TRI_BACK_GRAPH_INVENTORY` / `TRI_BACK_GRAPH_FACTORS` on those Knowledge Base paths. `Graphs/backups/red flags/v4/` is a local snapshot only.
- five `CONFIRM_AGAINST` rows: `Neuro sensory deficit` / `Neuro motor deficit` → CES (`r_45`, `r_46`); `Recent surgery` / `Refractory pain` / `Point tenderness` → Infection (`r_30`–`r_32`)

`ontology.py` already builds `factors_by_condition` from `parent_id` + `source_nodes` regardless of edge type, so those rows already make the CES / Infection hops. No extra ingest code, and no planner special case.

Because this is already live, **§2 is no longer a pre-ingest precaution — it is a live scoring leak.**

`update_graph.py` now copies both CSVs into every `_edges_` / `_factors_` promote, fails the pack on name mismatch or duplicates, and infers the sibling factors file when `--factors-csv` is omitted. That pack-level check is done. What remains in this phase is **runtime** loading (`csv_rows` / `ontology.py` / `get_factor_question_spec`).

### 2. Exclude `CONFIRM_AGAINST` from risk scoring

**This is the one non-obvious code change v4 still requires, and skipping it silently corrupts the disposition.**

The edge means "ask about this," not "this raises suspicion." `condition_ranker` / `inference` score path segments. If these edges reach the scorer, ordinary unilateral tingling starts ranking CES in the disposition and in the arm 2 narrative and arm 3 subgraph.

Filter the relationship type out of `score()` inputs while keeping it in traversal and coverage. It must also never reach the policy gate — a `CONFIRM_AGAINST` touch is a reason to ask, never a reason to escalate.

### 3. Askable-factor flag, from the v4 factors CSV

Do **not** hard-code an allow-list. `askable` is a column on `red_flags_factors_v4_2026.9.10.csv` (see §7). That is a node property: `Hypercoagulability`, `Venous stasis`, and `Endothelial injury` are each both a direct DVT factor and a mediator, and a patient still cannot answer them.

`askable=no` means the planner must not ask it. It does **not** drop the factor from matching or disposition. `Hypercoagulability` can still count as a matched DVT factor when inferred from `Diabetes` / `Hypertension`.

When a non-askable mediator would otherwise be the target, the askable factors that feed it are derivable from the existing mediated rows — no LLM inference needed (`Recent surgery` → `Endothelial injury`; `Prolonged bed rest` → `Venous stasis`; `Diabetes` / `Hypertension` → `Hypercoagulability`).

### 4. Expose `is_specific` per factor

`is_specific` is already parsed per row in `bot/app/services/graphrag/csv_rows.py` (`ChunkRow.is_specific`), but `RedFlagOntology` does not surface it per factor. Phase 3's first tie-break needs it. Small ontology extension; do it here so Phase 3 is purely planner work.

---

## Part B — Factor-question plumbing

### 5. `asked_factor` alongside the slot fields

`bot/app/orchestrator/state.py` has `last_asked_slot` (line 49) and `slot_being_asked` (line 50), both `SlotName | None`. Add:

```python
asked_factor: NotRequired[str | None]
```

Then fix the whole chain that assumes a slot was asked:

- **`generate_question_node`** only sets `last_asked_slot` when `slot_being_asked` is truthy. After a factor question, `last_asked_slot` therefore still points at the *previous* slot, and the next patient message gets credited to the wrong slot. Park or clear `last_asked_slot` on factor turns.
- **`_EMPTY_ANSWER`** in `slot_answers.py:52` matches `i don't know | idk | unsure | not sure | n/a | nothing | none | no idea | ?` but **not a bare "no"**. A patient answering "no" to "any saddle numbness?" would fall through `credit_asked_slot_answer` and be written in as a palliative or provocative answer. A bare "no" is a meaningful answer to a factor question and a non-answer to a slot question — these need different handling, not a shared regex.
- **`propose_checklist_enrichment(last_asked_slot=...)`** needs the factor equivalent or it drafts the wrong follow-up.

### 6. Factor-answer crediting path

A new path that takes the reply to a factor question and writes `factor_states[factor] = affirmed | denied | unknown`, using the Phase 1 negation machinery. "Not sure" stays `unknown`.

This is the join between the two phases: Phase 1 built the store and the polarity detector, this wires the ask-and-answer loop into it.

### 7. Factor question specs — v4 factors CSV

The authored table is **not** a Python file and **not** extra columns on the edge CSV. It is a sibling CSV that lives next to the edge table (Knowledge Base and `Graphs/backups/red flags/v4/source/`), one row per unique Factor node.

Authored layout (done 10 Sep 2026):

| file | role |
|---|---|
| `red_flags_edges_v4_2026.9.10.csv` | v3 relationship rows, unchanged columns |
| `red_flags_factors_v4_2026.9.10.csv` | node table |

| column | meaning |
|---|---|
| `source_nodes` (key) | same string as edge-table `source_nodes` / inventory Factor names |
| `askable` | `yes` / `no` — can a patient answer this? |
| `intent` | what the question must be about (binds the LLM, analogue of `slot_intake_brief`) |
| `fallback` | exact sentence if the LLM draft is rejected (analogue of `question_template`) |
| `synonyms` | ordinary patient language that counts as this factor |

Example (`Saddle anaesthesia`): `askable=yes`; `intent` = numbness around the groin, buttocks, inner thighs, genitals, or anus; `fallback` = Have you noticed any numbness around the groin or saddle area?; `synonyms` = saddle numbness; numbness in the saddle; perineal numbness.

**Why a second file, not edge columns.** The edge CSV is one row per factor→condition link. `Age over 50` and `Hypercoagulability` appear on several rows. `askable` / `intent` / `fallback` / `synonyms` are node properties; putting them on every edge row invites copy-paste drift. One factors-CSV row per unique name is the graph's node table.

**Coverage.** One row for every unique Factor name in the inventory (`source_nodes` ∪ `path` mediators that share the Factor label — 58 names). Path-only mediators still need `askable=no` or the planner cannot reject them. `Age over 50` / `Male sex` / `Female sex` are `askable=no`: they stay floor slots, not factor questions.

**Do not harvest `factor_patterns.py`.** That file maps volunteered checklist text → factor name. It has aliases for roughly a third of the inventory and **none** for `Bilat neuro sensory deficit` or `Bilat neuro motor deficit`. `chunk_string` is clinician evidence, not a patient question.

**Remaining code.** Teach `csv_rows` / `ontology.py` to load `TRI_BACK_GRAPH_FACTORS`. Pack promote already fails if a factors-CSV name is missing from the inventory, duplicated, or if an inventory factor has no sheet row (`update_graph.py`). Keep that check when the loaders are added so a hand-edited backup copy cannot drift.

Expose as `get_factor_question_spec(factor)` returning `askable`, `intent`, `fallback`, `synonyms`. Wording still goes through the existing pending-question path so the LLM phrases it, bound to `intent` + `fallback`. A missing spec, or `askable=no`, is not a legal ask target.

### 8. A test hook, not a behaviour change

Add a way to force a specific factor ask (a test-only entry point or a debug setting). Without it, this phase has nothing to verify end to end, and the first real exercise of the plumbing would be buried inside the Phase 3 ranker diff.

---

## Verification

- **Disposition is unchanged after the scoring filter.** Re-run the existing fixtures and diff condition rankings and disposition text against pre-filter v3. Any movement means `CONFIRM_AGAINST` leaked into `score()`. This is the single most important check in the phase.
- `factors_by_condition["CES"]` contains `Neuro sensory deficit` and `Neuro motor deficit` (true of the v4 pack; keep as a regression check).
- `get_factor_question_spec` is served from the v4 factors CSV: `Endothelial injury` is `askable=no` (and has no fallback), `Saddle anaesthesia` returns intent + fallback + synonyms, and `Hypercoagulability` can still count as a matched DVT factor.
- Pack validation rejects a factors CSV that is missing an inventory name or that duplicates a key (already true of `update_graph.py` on promote; keep as a loader regression).
- `RedFlagOntology` returns `is_specific` per factor.
- Via the test hook: a forced factor ask round-trips — the question is asked, "no" is recorded as `denied` (not credited to a slot), "yes" as `affirmed`, "not sure" as `unknown`, and `last_asked_slot` is not corrupted.
- Denial-adversarial fixtures from Phase 1 still pass.

## Risks

- **Silent scoring corruption.** If the `CONFIRM_AGAINST` exclusion is incomplete, nothing throws — the disposition just drifts toward CES. The pre/post diff above is the only thing that catches it.
- The bare-"no" split between factor answers and slot answers is easy to get half-right. A "no" to a factor question must not also reach `credit_asked_slot_answer`.

## User actions needed before this phase

From the parent plan's action list:

- ~~**Action 1 — finish the `CONFIRM_AGAINST` edge set.**~~ **Done.** Five edges in v3 (`r_30`–`r_32`, `r_45`, `r_46`). `Severe pain` → AAA was a candidate and was not added.
- ~~**Action 3 — author the v4 factor sheet.**~~ **Done 10 Sep 2026.** `red_flags_factors_v4_2026.9.10.csv` — 58 rows; `askable=no` for `Endothelial injury`, `Hypercoagulability`, `Venous stasis`, `Nutrient Deficiency`, `Vitamin Deficiency`, `Mechanical loading`, `Osteoporosis`, `Age over 50`, `Male sex`, `Female sex`. CES cluster first. Specs live in that CSV, not in `factor_patterns.py` and not as extra edge columns.
- ~~**Action 4 — promote the v4 backup pack.**~~ **Done 10 Sep 2026.** Local snapshot at `Graphs/backups/red flags/v4/`. `bot/.env` points `TRI_BACK_GRAPH_CSV` / `TRI_BACK_GRAPH_INVENTORY` / `TRI_BACK_GRAPH_FACTORS` at the Knowledge Base files (not Graphs). Aura instance wiped and reloaded from the edges CSV (86 rows / 58 factors / 7 conditions).
- ~~**Action 5 — a separate question-spec file.**~~ **Absorbed into action 3.**
