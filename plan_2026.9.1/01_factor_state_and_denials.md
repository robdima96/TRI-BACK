# Phase 1 — Factor state and denial-aware matching

**Status:** not started · **Prerequisite:** none · **Unblocks:** every other phase
**Parent design:** [graph_driven_intake.md](graph_driven_intake.md)

---

## Why this ships first

Nothing in this phase changes which questions the bot asks. It builds the substrate that makes graph questions safe to ask at all.

Factor matching today is **negation-blind**. Once the bot starts asking about red flags, it injects that vocabulary into the conversation, and the patient echoes it back in denials:

> bot: "Any bladder problems?" → patient: "no bladder problems" → `Bladder dysfunction` matched → (once Phase 4 lands) hard escalate → **false ED referral caused by the question meant to protect the patient.**

If any later phase ships before this one, the feature actively makes the bot less safe than it is today. That is the entire ordering constraint in this plan set.

## Scope

In:

- A three-state per-factor memory on `ChatState`.
- Negation handling in the factor matcher.
- Closing the three known false-affirm paths.
- A denial-adversarial fixture set running in CI.

Out (later phases): asking factor questions, graph v3, ranking, escalation, arm 3.

---

## The three known false-affirm paths

All three are live today and all three must be neutralised here.

1. **Bare-token aliases.** `_TEXT_ALIASES` in `bot/app/services/rag/factor_patterns.py` maps the bare token `"bladder"` → `Bladder dysfunction` and `"bowel"` → `Bowel dysfunction`, word-bounded against raw checklist text. Any sentence containing the word matches, including a denial.
2. **Raw reply written into the checklist.** `credit_asked_slot_answer` (`bot/app/orchestrator/slot_answers.py:86`) writes the patient's message into the checklist as a row, so the denial text becomes matchable content.
3. **Fuzzy fallback.** `factor_matcher.py` accepts on token overlap ≥ 0.75 (`overlap = len(text_tokens & factor_tokens) / len(factor_tokens)`, `score = overlap * 0.75`). "no bowel dysfunction" scores 1.0 against `Bowel dysfunction`; "no calf pain" clears the threshold against `Calf pain` outright.

Note that LLM factor matching cannot rescue this: `eligible_for_llm_match` in `bot/app/services/rag/llm_factor_match.py` returns `False` when `match.factor_name` is already set, so the LLM can only *add* matches, never remove a false positive.

---

## Changes

### 1. `factor_states` on `ChatState`

Add to `bot/app/orchestrator/state.py`, alongside the existing `matched_factors` (line 58):

```python
factor_states: NotRequired[dict[str, str]]  # canonical Factor name -> unknown|affirmed|denied
```

**Do not** put polarity on `ChecklistItem`. `content_dedupe_key` is `(text, kind, source, label)`, so an affirmed row and a denied row for the same finding collide, and a polarity field would ripple into `merge_checklist_items`, the enricher contract, coverage, and session JSON. A separate map is additive, is exactly what the Phase 3 ranker consumes, and serialises cleanly through the checkpointer.

Absent key and `"unknown"` are equivalent. "I'm not sure" stays `unknown`, never `denied`.

### 2. Negation detection in the matcher

Scope negation to the **span** around the candidate match, not the whole message — "my back is killing me but no bowel problems" must affirm nothing and deny `Bowel dysfunction`, not deny the back pain.

- Detect a negation cue (`no`, `not`, `denies`, `never`, `without`, `haven't had`, `nothing like`) within a bounded window before the matched span, stopping at a conjunction or clause boundary.
- On a negated match, write `factor_states[factor] = "denied"` and **exclude the factor from `matched_factors`**.
- On an affirmed match, write `factor_states[factor] = "affirmed"` and keep existing behaviour.
- Denials are sticky within a session unless the patient later affirms.

### 3. Tighten the two weakest match paths

- Require the bare tokens `"bladder"` and `"bowel"` to co-occur with a dysfunction cue (problem, incontinence, retention, control, accident, leaking) rather than matching alone. Same treatment for the short DVT aliases `"calf ache"` and `"leg swelling"`.
- Make the fuzzy fallback refuse to fire when a negation cue is present in the span. Raising the threshold does not help — the denial phrase scores *higher* than the affirmation, because it contains the factor name verbatim.

### 4. Persist it

Add `factor_states` to the session snapshot so denials survive a reload. `build_orchestrator_snapshot` in `bot/app/session_enrichment.py` is the natural home; note that `build_disposition_record` returns `None` on question turns, so that path is not available.

### 5. Denial-adversarial fixtures in CI

A fixture set where the actor denies every red flag using the bot's own vocabulary: "no bladder problems", "no numbness in the saddle area", "no bowel dysfunction", "no calf pain or swelling", "no fever", "no weight loss".

Assert across the whole set:

- **Zero** affirmed factors.
- **Zero** escalations (trivially true today; becomes the load-bearing assertion in Phase 4).
- Every denied factor appears in `factor_states` as `denied`, so Phase 3 will not re-ask it.

This runs in CI, not once by hand. It is the regression test that protects every later phase.

---

## Verification

This phase is correct when the bot's *observable behaviour is unchanged* and the new state is populated correctly.

- Question order, question count, and disposition text are byte-identical to today on the existing fixtures. Any diff here is a bug in this phase, not an intended change.
- The denial fixture set passes with zero affirmed factors.
- A session that mentions a real red flag affirmatively still matches it — check that the negation window has not become so wide it swallows affirmations in compound sentences.
- `factor_states` round-trips through the checkpointer and appears in the session JSON.

## Risks

- **Over-broad negation windows** silently suppress true positives. This is the failure mode that matters clinically, and it is invisible in the denial fixtures because those contain no affirmations. Include mixed affirm-and-deny sentences in the fixture set specifically to catch it.
- Tightening `"bladder"` / `"bowel"` aliases may drop matches that currently fire on terse phrasing ("bladder issues since Tuesday"). Check the cue list covers ordinary patient language before merging.

## User actions needed before this phase

- **Denial phrasebook** (parent plan, action 7): representative patient denial wordings per CES / AAA / DVT factor. Needed to seed both the negation cue list and the fixture set. This is the only blocking item for Phase 1.
