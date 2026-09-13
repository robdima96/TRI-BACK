"""Study-app graph schema literals stay in lockstep with the bot copy."""

from typing import get_args

from digimsk_study_app.graph.schemas import TraversalAction, TraversalMode


def test_schema_literals_include_intake_actions():
    assert "ask_factor" in get_args(TraversalAction)
    assert "deny_factor" in get_args(TraversalAction)
    assert "graph_gap" in get_args(TraversalAction)
    assert get_args(TraversalMode) == ("traversal", "intake_gap")
