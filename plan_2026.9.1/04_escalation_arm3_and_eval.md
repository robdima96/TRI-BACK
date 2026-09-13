# Phase 4 — Escalation, arm 3 views, and evaluation

**Status:** not started · **Prerequisite:** [Phase 1](01_factor_state_and_denials.md), [Phase 2](02_graph_v3_and_factor_asks.md) and [Phase 3](03_relevance_ranker.md) merged
**Parent design:** [graph_driven_intake.md](graph_driven_intake.md)

---

## Why this is last

Two independent reasons, and both are hard ordering constraints rather than preferences.

**Escalation is last because it is the only irreversible output.** Every earlier phase can be wrong and produce a slightly odd interview. This phase can send someone to the emergency department. It must not ship until denial handling (Phase 1) has been running against the far higher volume of red-flag vocabulary that Phase 3 generates.

**Arm 3 is last because it visualises the ranker.** There is nothing to draw until Phase 3 produces `question_reason`.

The two are grouped because both are consumers of the finished pipeline rather than parts of it. If you want a smaller review unit, split at Part A / Part B — Part A is safety-critical and Part B is presentational, and they share no code.

---

## Part A — Escalation

Hard escalate in `bot/app/orchestrator/policy.py` is currently only suicide/self-harm, chest pain, and respiratory distress. It gains LBP red flags here.

### 1. Gate on polarity, never on membership

```
escalate on factor_states[factor] == "affirmed"
never on membership in matched_factors
```

This is non-negotiable and is the whole reason Phase 1 exists. `matched_factors` is negation-blind by construction.

`CONFIRM_AGAINST` touches must not reach the gate either. That edge means "ask about this", never "this raises suspicion". Only affirmed `SUGGESTIVE_OF` / `TRIGGER_FOR` factors count.

### 2. Clusters, not isolated findings

Do **not** escalate on any single affirmed factor in the high-acuity clusters. `Bladder dysfunction` alone in an older patient with chronic urinary symptoms is a routine false positive, and `prompts/clinical_reasoning_framework.md` is built on "clusters, not isolated findings."

Escalate on either:

- a named short list of genuinely standalone triggers (`Saddle anaesthesia`, new `Bilat neuro motor deficit` / `Bilat neuro sensory deficit`), **or**
- any other CES / AAA / DVT factor affirmed **together with** the spinal-pain anchor.

DVT makes this especially important: `Calf pain` and `Calf swelling` are individually common and benign, and the graph itself says each "alone is not an indicator" (`r_60`–`r_62`). DVT escalates on a **combination plus laterality**, never on one calf symptom.

### 3. Disposition can decline to advise

`disposition_brief.py` today flags unmatched rows as `insufficient_evidence` and then drafts advice anyway. Allow the disposition to return to a factor question, or to an explicit insufficient-information response, rather than only softening the wording. This is the counterpart to the Phase 3 budget rule: exhausting the budget with a time-critical factor unknown must produce "not enough to advise", not a self-care dump.

---

## Part B — Arm 3 graph views

Study arm 3 renders `graph_traversal` as Cytoscape today, but that payload is built only at **disposition**, and question turns clear it in `generate_question_node`. The panel can show "why this advice" and never "why this question."

Ship **both** views; decide later whether the UI keeps one, the other, or both.

### 4. View A — disposition subgraph (unchanged)

Matched factors → real CSV/Neo4j paths → conditions, with the current highlight and step list. Built by `graph_traversal_node` / agentic provenance, same `GraphTraversalTrace` shape as today. No work beyond leaving it alone.

### 5. View B — intake planner slice (new)

Same payload shape, different slice and `mode` (`intake_gap` vs today's `traversal`). Built on question turns and accumulated across the interview.

Draw **only edges the v4 edges CSV already contains**. The factors CSV is node metadata (`askable`, `intent`, `fallback`, `synonyms`) — never invent edges from it, and do not render `intent` / `fallback` / `synonyms` as graph relationships.

- Affirmed factors: filled, as today.
- Denied factors: same nodes, dimmed. This is session state from `factor_states`, not a graph edit.
- Current ask target: dashed / highlighted. Only a factor with `askable=yes` on the factors CSV can be an ask target.
- Non-askable mechanism nodes may appear as mediators on a path; they are not ask targets.
- Edges: the real `RISK_FACTOR_FOR` / `SUGGESTIVE_OF` / `CONTRIBUTES_TO` / `CONFIRM_AGAINST` links those nodes already have.

Draw `CONFIRM_AGAINST` in a visually distinct style, so a "we are asking about this" edge never reads as "this points to CES."

The step list carries the ranking rationale from Phase 3's `question_reason`. **Invent no edges.** New relationship types are a clinical-content decision reviewed in the edges CSV, never a visualization convenience.

### 6. Use a separate field — do not reuse `graph_traversal`

The clear in `generate_question_node` is deliberate: it stops a previous turn's disposition subgraph from being re-served alongside a later question. Since both views should be live, a second field beats one contested slot.

- Add `intake_traversal: NotRequired[dict | None]` to `ChatState` and `ChatResponse`.
- Keep the existing `graph_traversal` clear on question turns exactly as it is.
- View B writes `intake_traversal` on question turns; View A keeps writing `graph_traversal` at disposition and escalate.

### 7. Widen the schema literals in both hand-mirrored files

`mode` is `Literal["traversal"]` in `bot/app/services/graphrag/schemas.py` **and** in the duplicated study-app copy `prototypes/digimsk_study_app/digimsk_study_app/graph/schemas.py`. `TraversalAction` is likewise a closed literal in both.

Adding `intake_gap` plus the new step actions (`graph_gap`, `ask_factor`, `deny_factor`) without editing **both** will fail Pydantic validation in the study app. `scripts/sync_digimsk_cytoscape.py` syncs the Cytoscape JS but **not** these schemas — the mirror is manual.

### 8. Persistence

`build_disposition_record` returns `None` whenever `question_mode` is true, so nothing from a question turn currently reaches `disposition_history`. `build_orchestrator_snapshot` logs `question_reason` and `slot_being_asked` but carries no graph payload.

The accumulating `intake_steps[]` (match → rank → ask → affirm/deny) needs a home: extend `build_orchestrator_snapshot` or add a sibling `intake_history` record.

Study app: same Cytoscape path, with `mode` plus two keyed payloads (`intake` and `disposition`) so the client can show either or both.

---

## Verification

Safety, and this is the phase where it counts:

- The Phase 1 denial-adversarial fixture set asserts **zero escalations**. Until this phase that assertion was trivially true. Now it is the real test, and it must run in CI.
- A single affirmed `Bladder dysfunction` with no anchor and no second factor does **not** escalate. A `Saddle anaesthesia` affirmation does.
- One affirmed calf symptom does not escalate DVT; a combination plus laterality does.

Arm 3:

- A factor turn includes a planner slice on `intake_traversal` whose highlighted factor matches that turn's `question_reason`.
- A later disposition turn still includes the matched-path subgraph on `graph_traversal`. Neither overwrites the other.
- The study app parses both payloads without Pydantic errors — the check that catches a half-done schema mirror.
- Diff the graph relationship types rendered against the v4 **edges** CSV. No type appears that that file does not define. Factors-CSV columns must not show up as edge types.

Persistence:

- `factor_states` and `intake_steps[]` survive a session reload.

## Risks

- **Escalating on a denial** is the catastrophic failure of this whole plan set. The gate reading `factor_states` rather than `matched_factors` is the single line that prevents it; make it explicit in code, not implied by a helper.
- **Half-mirrored schemas.** Editing only the bot copy passes bot tests and fails in the study app at run time. Create a test that imports both and asserts the literals are equal.
- Escalation thresholds are clinical, not technical. Do not tune them to make a fixture pass.

## User actions needed before this phase

- **Action 6 — the standalone escalation list.** Which affirmed factors justify immediate ED referral on their own, versus which require the spinal-pain anchor or a second factor. Current suggestion: `Saddle anaesthesia` and the new bilateral deficits stand alone; `Bladder dysfunction` / `Bowel dysfunction` do not. This gates Part A.
- **Action 10 — arm 3 presentation.** Whether the study UI shows View A only, View B only, or both, and whether View B appears mid-interview or only in the post-hoc record. Both payloads are produced regardless, so this gates the UI work only, not the backend.

The v4 pack is already ingested by this phase (`red_flags_edges_v4_…` + `red_flags_factors_v4_…`). View B uses the factors CSV as node metadata only (`askable` to know what can be an ask target). Do not add visualization-only columns or edges.
