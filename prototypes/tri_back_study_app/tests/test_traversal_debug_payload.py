"""Tests for per-condition traversal debug payloads."""

from tri_back_study_app.graph.cytoscape_builder import (
    build_traversal_debug_payload,
    traversal_debug_json,
)
from tri_back_study_app.graph.schemas import (
    ConditionRisk,
    ConditionTraversal,
    GraphTraversalTrace,
    TraversalStep,
)


def test_build_traversal_debug_payload_groups_conditions():
    trace = GraphTraversalTrace(
        trace_id="t1",
        title="Test traversal",
        shared_steps=[
            TraversalStep(step=1, action="match_factor", factor="Severe pain"),
        ],
        condition_risks=[
            ConditionRisk(condition="Fracture", risk_score=5.5, path_count=2),
            ConditionRisk(condition="Infection", risk_score=2.0, path_count=1),
        ],
        condition_traversals=[
            ConditionTraversal(
                condition="Fracture",
                risk_score=5.5,
                rank=1,
                path_count=2,
                supporting_factors=["Severe pain"],
                steps=[
                    TraversalStep(
                        step=2,
                        action="traverse_direct",
                        factor="Severe pain",
                        condition="Fracture",
                        relationship="RISK_FACTOR_FOR",
                    )
                ],
            ),
            ConditionTraversal(
                condition="Infection",
                risk_score=2.0,
                rank=2,
                path_count=1,
                supporting_factors=["Fever"],
                steps=[
                    TraversalStep(
                        step=3,
                        action="traverse_direct",
                        factor="Fever",
                        condition="Infection",
                        relationship="SUGGESTIVE_OF",
                    )
                ],
            ),
        ],
    )
    payload = build_traversal_debug_payload(trace)
    assert len(payload["conditions"]) == 2
    assert payload["conditions"][0]["condition"] == "Fracture"
    assert payload["conditions"][0]["riskScore"] == 5.5
    assert payload["sharedSteps"][0]["summary"].startswith("Matched factor")

    raw = traversal_debug_json(trace)
    assert "Fracture" in raw
    assert "Infection" in raw


def test_traversal_step_accepts_confirmed_bool():
    step = TraversalStep.model_validate(
        {
            "step": 1,
            "action": "checklist_item",
            "checklist_item": {
                "text": "low back pain",
                "kind": "symptom",
                "source": "pattern",
                "label": "symptom",
                "id": "c1",
                "confirmed": False,
            },
        }
    )
    assert step.checklist_item["confirmed"] is False
    trace = GraphTraversalTrace.model_validate(
        {
            "trace_id": "t-confirmed",
            "title": "confirmed-bool",
            "steps": [step.model_dump()],
        }
    )
    assert trace.steps[0].checklist_item["confirmed"] is False
