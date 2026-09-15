"""Pluggable condition inference interface for deterministic GraphRAG.

The heuristic adapter preserves current behavior. ``BayesianConditionScorer``
is intentionally a configuration skeleton only: it fails clearly until priors,
conditional probabilities, and calibration metadata are supplied.
"""

from __future__ import annotations

from typing import Protocol

from app.services.graphrag.graph_client_protocol import PathSegment
from app.services.graphrag.schemas import ConditionRisk


class ConditionScorer(Protocol):
    """Convert grounded path segments into auditable condition scores."""

    name: str

    def score(self, segments: list[PathSegment]) -> list[ConditionRisk]: ...


class _ExcludeConfirmAgainstScorer:
    """Drop CONFIRM_AGAINST before any scorer, including a future Bayesian model."""

    def __init__(self, inner: ConditionScorer) -> None:
        self._inner = inner
        self.name = inner.name

    def score(self, segments: list[PathSegment]) -> list[ConditionRisk]:
        from app.services.graphrag.condition_ranker import scoring_segments

        return self._inner.score(scoring_segments(segments))


class HeuristicConditionScorer:
    name = "heuristic"

    def score(self, segments: list[PathSegment]) -> list[ConditionRisk]:
        from app.services.graphrag.condition_ranker import score_conditions

        return score_conditions(segments)


class BayesianNotConfiguredError(RuntimeError):
    """Raised when Bayesian inference is selected before a model exists."""


class BayesianConditionScorer:
    name = "bayesian"

    def score(self, segments: list[PathSegment]) -> list[ConditionRisk]:
        _ = segments
        raise BayesianNotConfiguredError(
            "TRI_BACK_GRAPH_INFERENCE=bayesian is not configured yet. "
            "Provide reviewed priors/CPTs (or a calibrated noisy-OR model) "
            "before enabling Bayesian condition scoring."
        )


def get_condition_scorer(name: str | None = None) -> ConditionScorer:
    from app.config import settings

    selected = (name or settings.graph_inference).strip().lower()
    if selected == "heuristic":
        inner: ConditionScorer = HeuristicConditionScorer()
    elif selected == "bayesian":
        inner = BayesianConditionScorer()
    else:
        raise ValueError(f"Unsupported graph inference backend: {selected!r}")
    return _ExcludeConfirmAgainstScorer(inner)
