"""Read-only local tools the disposition agent may call.

Every tool reads exclusively from the ground-truth red-flags graph
(``red_flags_manual_failsafe.csv`` via :class:`LocalGraphClient` /
``traverse_from_turn``) or the local Chroma corpus. None of them accept
free-text clinical claims from the model - the agent can only *retrieve and
inspect* what already exists. Condition/factor arguments are validated against
the ontology so the agent cannot query fictional entities.

Each call returns a :class:`ToolResult` carrying a bounded observation string
(fed back to the model) plus structured provenance (factors / conditions /
chunk_ids) recorded in the audit trace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.schemas import ChecklistItem, ChunkMatch
from app.services.agentic_graph_rag.ontology import (
    RedFlagOntology,
    load_ontology,
    tally_touched_conditions,
)

_MAX_OBS_CHARS = 1400
_MAX_SNIPPET_CHARS = 320


def _clip(text: str, limit: int = _MAX_OBS_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


@dataclass
class ToolContext:
    """Per-turn inputs the tools operate over (all ground-truth derived).

    Factor matches are precomputed once as shared intake preparation; graph and
    RAG evidence is retrieved lazily through tools selected by the agent.
    """

    checklist: list[dict[str, str]]
    chunk_matches: list[ChunkMatch]
    ontology: RedFlagOntology
    query: str = ""
    precomputed_matched_factors: list[str] | None = None
    precomputed_factor_matches: list[Any] | None = None


# ---------------------------------------------------------------------------
# Tool implementations (import heavy deps lazily, mirroring orchestrator nodes)
# ---------------------------------------------------------------------------

from app.services.agentic_graph_rag.schemas import ToolResult  # noqa: E402


def _checklist_items(ctx: ToolContext) -> list[ChecklistItem]:
    out: list[ChecklistItem] = []
    for row in ctx.checklist:
        if isinstance(row, ChecklistItem):
            out.append(row)
        else:
            out.append(ChecklistItem.model_validate(row))
    return out


def tool_get_matched_factors(ctx: ToolContext, **_: Any) -> ToolResult:
    """Which red-flag Factors the current checklist matched (ground truth)."""
    if ctx.precomputed_matched_factors is not None:
        matched = list(ctx.precomputed_matched_factors)
        unmatched: list[str] = []
        if ctx.precomputed_factor_matches is not None:
            for m in ctx.precomputed_factor_matches:
                name = getattr(m, "factor_name", None)
                if name:
                    continue
                item = getattr(m, "checklist_item", None) or {}
                if isinstance(item, dict):
                    text = (item.get("text") or "").strip()
                else:
                    text = str(getattr(item, "text", "") or "").strip()
                if text:
                    unmatched.append(text)
        obs = {
            "matched_factors": matched,
            "unmatched_checklist_text": unmatched[:12],
            "source": "precomputed_traversal",
        }
        return ToolResult(
            name="get_matched_factors",
            observation=_clip(json.dumps(obs, ensure_ascii=False)),
            data=obs,
            factors=matched,
        )

    from app.services.graphrag import match_checklist_to_factors

    matches = match_checklist_to_factors(ctx.checklist)
    matched = [m.factor_name for m in matches if m.factor_name]
    unmatched = [
        (m.checklist_item.get("text") or "")
        for m in matches
        if not m.factor_name
    ]
    obs = {
        "matched_factors": matched,
        "unmatched_checklist_text": [u for u in unmatched if u][:12],
    }
    return ToolResult(
        name="get_matched_factors",
        observation=_clip(json.dumps(obs, ensure_ascii=False)),
        data=obs,
        factors=matched,
    )


def tool_list_touched_conditions(ctx: ToolContext, **_: Any) -> ToolResult:
    """Unranked condition membership hits for the turn's matched factors."""
    if ctx.precomputed_matched_factors is not None:
        matched = list(ctx.precomputed_matched_factors)
    else:
        matches = tool_get_matched_factors(ctx)
        matched = list(matches.factors)
    touched = tally_touched_conditions(matched, ctx.ontology)
    obs = {
        "matched_factors": matched,
        "touched_conditions": touched,
        "interpretation": (
            "Unranked factor-membership hit counts only; not risk scores, "
            "probabilities, or a disposition ranking."
        ),
    }
    return ToolResult(
        name="list_touched_conditions",
        observation=_clip(json.dumps(obs, ensure_ascii=False)),
        data=obs,
        factors=matched,
        conditions=[str(row["condition"]) for row in touched],
    )


def tool_get_factor_paths(ctx: ToolContext, factors: list[str] | None = None, **_: Any) -> ToolResult:
    """Ground-truth graph paths (Factor -[rel]-> [mediator] -> Condition) for factors."""
    from app.services.graphrag import get_graph_client

    requested = [f for f in (factors or []) if isinstance(f, str) and f.strip()]
    if not requested:
        return ToolResult(
            name="get_factor_paths",
            ok=False,
            error="no factors provided",
            observation="Provide a non-empty 'factors' list (use exact Factor names).",
        )

    known = ctx.ontology.factor_set()
    valid = [f for f in requested if f in known]
    unknown = [f for f in requested if f not in known]

    client = get_graph_client()
    segments = client.paths_for_factors(valid) if valid else []
    paths: list[dict[str, Any]] = []
    chunk_ids: list[str] = []
    conditions: list[str] = []
    for seg in segments:
        if seg.via_mediation and seg.mediator:
            desc = f"{seg.factor} -[{seg.relationship}]-> {seg.mediator} -> {seg.condition}"
        else:
            desc = f"{seg.factor} -[{seg.relationship}]-> {seg.condition}"
        paths.append({"path": desc, "chunk_id": seg.chunk_id, "is_specific": seg.is_specific})
        if seg.chunk_id:
            chunk_ids.append(seg.chunk_id)
        conditions.append(seg.condition)

    obs = {"paths": paths[:20]}
    if unknown:
        obs["ignored_unknown_factors"] = unknown
    return ToolResult(
        name="get_factor_paths",
        observation=_clip(json.dumps(obs, ensure_ascii=False)),
        data=obs,
        factors=valid,
        conditions=list(dict.fromkeys(conditions)),
        chunk_ids=list(dict.fromkeys(chunk_ids)),
    )


def tool_get_condition_evidence(ctx: ToolContext, condition: str | None = None, **_: Any) -> ToolResult:
    """All ground-truth paths + chunk snippets that point at one Condition."""
    from app.services.graphrag import get_graph_client

    if not condition or not isinstance(condition, str):
        return ToolResult(
            name="get_condition_evidence",
            ok=False,
            error="no condition provided",
            observation="Provide 'condition' (one of the ontology conditions).",
        )
    if condition not in ctx.ontology.condition_set():
        return ToolResult(
            name="get_condition_evidence",
            ok=False,
            error=f"unknown condition {condition!r}",
            observation=(
                f"{condition!r} is not in the graph. Valid: "
                + ", ".join(ctx.ontology.conditions)
            ),
        )

    factors = ctx.ontology.factors_by_condition.get(condition, ())
    client = get_graph_client()
    segments = client.paths_for_factors(list(factors))
    paths: list[dict[str, Any]] = []
    chunk_ids: list[str] = []
    for seg in segments:
        if seg.condition != condition:
            continue
        if seg.via_mediation and seg.mediator:
            desc = f"{seg.factor} -[{seg.relationship}]-> {seg.mediator} -> {seg.condition}"
        else:
            desc = f"{seg.factor} -[{seg.relationship}]-> {seg.condition}"
        entry: dict[str, Any] = {"path": desc, "chunk_id": seg.chunk_id}
        if seg.chunk_string:
            entry["snippet"] = seg.chunk_string[:_MAX_SNIPPET_CHARS]
        paths.append(entry)
        if seg.chunk_id:
            chunk_ids.append(seg.chunk_id)

    obs = {"condition": condition, "supporting_factors": list(factors), "paths": paths[:16]}
    return ToolResult(
        name="get_condition_evidence",
        observation=_clip(json.dumps(obs, ensure_ascii=False)),
        data=obs,
        factors=list(factors),
        conditions=[condition],
        chunk_ids=list(dict.fromkeys(chunk_ids)),
    )


def tool_search_evidence(ctx: ToolContext, query: str | None = None, **_: Any) -> ToolResult:
    """Semantic + lexical chunk retrieval over the local corpus (read-only)."""
    from app.config import settings
    from app.services.rag.chunk_retrieval import retrieve_rag_chunk_matches

    q = (query or ctx.query or "").strip()
    if not q:
        return ToolResult(
            name="search_evidence",
            ok=False,
            error="no query provided",
            observation="Provide a 'query' string to search local evidence.",
        )
    if not settings.rag_load:
        return ToolResult(
            name="search_evidence",
            ok=False,
            error="rag disabled",
            observation="Chroma RAG is disabled (DIGIMSK_RAG=0); use graph tools instead.",
        )

    matches = retrieve_rag_chunk_matches(q, None, ctx.checklist, top_k=5)
    hits = [
        {"chunk_id": m.chunk_id, "score": round(m.score, 3), "snippet": m.snippet[:_MAX_SNIPPET_CHARS]}
        for m in matches
    ]
    obs = {"query": q, "hits": hits}
    return ToolResult(
        name="search_evidence",
        observation=_clip(json.dumps(obs, ensure_ascii=False)),
        data=obs,
        chunk_ids=[m.chunk_id for m in matches],
    )


def tool_score_conditions_bayesian(ctx: ToolContext, **_: Any) -> ToolResult:
    """Reserved tool contract for a future reviewed Bayesian model."""
    _ = ctx
    return ToolResult(
        name="score_conditions_bayesian",
        ok=False,
        error="bayesian model not configured",
        observation=(
            "Bayesian condition scoring is a disabled interface skeleton. "
            "No priors/CPTs or calibrated noisy-OR parameters are configured."
        ),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: dict[str, str]  # arg name -> human description
    func: Callable[..., ToolResult]


_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_matched_factors",
        description="List red-flag Factors matched from the current checklist (and unmatched text).",
        arguments={},
        func=tool_get_matched_factors,
    ),
    ToolSpec(
        name="list_touched_conditions",
        description=(
            "List conditions touched by matched factors with unranked membership "
            "hit counts (not probabilities or risk scores)."
        ),
        arguments={},
        func=tool_list_touched_conditions,
    ),
    ToolSpec(
        name="get_factor_paths",
        description="Show ground-truth graph paths for specific Factor names (exact names).",
        arguments={"factors": "list of exact Factor names to expand"},
        func=tool_get_factor_paths,
    ),
    ToolSpec(
        name="get_condition_evidence",
        description="Show supporting factors, paths, and chunk snippets for one Condition.",
        arguments={"condition": "one condition name from the ontology"},
        func=tool_get_condition_evidence,
    ),
    ToolSpec(
        name="search_evidence",
        description="Semantic/lexical search of the local evidence corpus; returns chunk_ids + snippets.",
        arguments={"query": "a focused clinical query string"},
        func=tool_search_evidence,
    ),
    ToolSpec(
        name="score_conditions_bayesian",
        description=(
            "Future probabilistic condition scorer; unavailable until a reviewed "
            "Bayesian model is configured."
        ),
        arguments={},
        func=tool_score_conditions_bayesian,
    ),
)

_TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in _TOOL_SPECS}

# Tools that require GraphRAG / Chroma respectively.
_GRAPH_TOOL_NAMES = frozenset(
    {
        "get_factor_paths",
        "get_condition_evidence",
    }
)
_RAG_TOOL_NAMES = frozenset({"search_evidence"})
_BAYESIAN_TOOL_NAMES = frozenset({"score_conditions_bayesian"})


def _active_tool_specs() -> tuple[ToolSpec, ...]:
    """Filter the static catalog by runtime DIGIMSK_RAG / DIGIMSK_GRAPH_RAG toggles."""
    from app.config import settings

    out: list[ToolSpec] = []
    for spec in _TOOL_SPECS:
        if spec.name in _BAYESIAN_TOOL_NAMES and not settings.agentic_bayesian_tool:
            continue
        if spec.name in _RAG_TOOL_NAMES and not settings.rag_load:
            continue
        if spec.name in _GRAPH_TOOL_NAMES and not settings.graphrag_load:
            continue
        out.append(spec)
    return tuple(out)


def tool_specs() -> tuple[ToolSpec, ...]:
    return _active_tool_specs()


def tool_names() -> list[str]:
    return [t.name for t in _active_tool_specs()]


def render_tool_catalog() -> str:
    """Human/LLM-readable catalog of tools and arguments for the prompt."""
    lines: list[str] = []
    for spec in _active_tool_specs():
        if spec.arguments:
            args = "; ".join(f"{k} ({v})" for k, v in spec.arguments.items())
        else:
            args = "(no arguments)"
        lines.append(f"- {spec.name}: {spec.description} Args: {args}")
    return "\n".join(lines)


def invoke_tool(name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Dispatch a validated tool call; unknown/disabled tools return an error result."""
    active = {t.name: t for t in _active_tool_specs()}
    spec = active.get(name)
    if spec is None:
        available = ", ".join(active) or "(none)"
        return ToolResult(
            name=name,
            ok=False,
            error="unknown or disabled tool",
            observation=(
                f"Unknown or disabled tool {name!r}. Available: {available}"
            ),
        )
    args = arguments if isinstance(arguments, dict) else {}
    try:
        return spec.func(ctx, **args)
    except TypeError as exc:
        return ToolResult(
            name=name,
            ok=False,
            error=f"bad arguments: {exc}",
            observation=f"Invalid arguments for {name!r}: {exc}",
        )
    except Exception as exc:  # pragma: no cover - defensive; tools stay read-only
        return ToolResult(
            name=name,
            ok=False,
            error=str(exc),
            observation=f"Tool {name!r} failed: {exc}",
        )
