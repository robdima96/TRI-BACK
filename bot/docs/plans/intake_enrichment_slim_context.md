# Plan: Slim per-turn intake enrichment (efficiency)

Status: **implemented** (see `intake_enricher.py`)

## Goals

- Keep per-turn LLM enrichment for conversational `next_intake` and checklist oversight.
- Cut input tokens and latency substantially.
- Keep add/modify/delete visible in logs; rely on audit + session lab for post-hoc review.

## Implementation summary

- Replaced full `messages[]` transcript replay with a **single instruction** user message.
- Context: last assistant question + latest patient message + checklist + coverage gaps.
- Removed duplicate transcript block inside the instruction.
- Reduced `INTAKE_ENRICH_MAX_NEW_TOKENS` from 4096 to **1536**.
- `conversation_history` retained on API for backward compatibility; only the last
  assistant turn is extracted when `last_assistant_message` is omitted.

## Non-goals

- No removal of per-turn enrichment.
- No add-only restriction (delete remains allowed).
- Disposition-time completeness pass remains a separate track.
