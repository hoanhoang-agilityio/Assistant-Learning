from pathlib import Path

import pytest
from langgraph.types import Command

from core.graph.builder import build_graph
from core.hitl.resume import MAX_REVISION_COUNT, create_approval_decision, decision_to_resume_update
from core.hitl.utils import request_approval_data
from tests.helpers.hitl import pause_before_hitl, run_to_hitl_pause


def test_request_approval_sets_waiting_state() -> None:
    result = request_approval_data("# Draft plan content", {"passed": True})
    assert result["waiting_for_user"] is True
    assert result["hitl_type"] == "approval"
    assert result["verification_passed"] is True


def test_graph_interrupts_before_hitl_and_resumes_to_persist(tmp_path: Path) -> None:
    graph = build_graph()
    config = pause_before_hitl(graph, "hitl-run", tmp_path)

    snapshot = graph.get_state(config)
    assert snapshot.next == ("hitl",)

    resumed = graph.invoke(
        Command(
            update={
                "user_response": "approve",
                "approval_status": "approved",
                "waiting_for_user": False,
            }
        ),
        config,
    )
    assert resumed["approval_status"] == "approved"
    assert resumed["current_node"] == "persist"
    assert resumed["final_artifact_path"] is not None

    final_snapshot = graph.get_state(config)
    assert final_snapshot.next == ()


def test_graph_reject_at_approval_ends_without_persist(tmp_path: Path) -> None:
    graph = build_graph()
    config = pause_before_hitl(graph, "hitl-reject-run", tmp_path)

    resumed = graph.invoke(
        Command(
            update={
                "user_response": "Rejected the plan.",
                "approval_status": "rejected",
                "waiting_for_user": False,
            }
        ),
        config,
    )
    assert resumed["approval_status"] == "rejected"
    assert resumed.get("final_artifact_path") is None
    snapshot = graph.get_state(config)
    assert snapshot.next == ()


def test_graph_interrupts_on_hitl_route_and_resumes_to_persist(tmp_path: Path) -> None:
    """Approving must persist even when verification did not fully pass."""
    graph = build_graph()
    config = pause_before_hitl(
        graph,
        "hitl-failed-verification-run",
        tmp_path,
        verification_passed=False,
        faithfulness_score=0.5,
    )

    snapshot = graph.get_state(config)
    assert snapshot.next == ("hitl",)

    resumed = graph.invoke(
        Command(
            update={
                "user_response": "approve",
                "approval_status": "approved",
                "waiting_for_user": False,
            }
        ),
        config,
    )
    assert resumed["approval_status"] == "approved"
    assert resumed["current_node"] == "persist"
    assert resumed["final_artifact_path"] is not None

    final_snapshot = graph.get_state(config)
    assert final_snapshot.next == ()


def test_graph_revision_routes_back_to_fitness(tmp_path: Path, complete_profile: dict) -> None:
    graph = build_graph()
    config = run_to_hitl_pause(
        graph,
        "hitl-revision-run",
        tmp_path,
        query="I want a 4-day training plan to lose weight with strength training.",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    assert graph.get_state(config).next == ("hitl",)

    update = decision_to_resume_update(
        create_approval_decision(
            "revision",
            message="Reduce training volume and add more recovery days.",
        ),
        revision_count=0,
    )
    assert update["revision_count"] == 1
    assert update["revision_feedback"] == "Reduce training volume and add more recovery days."
    # Left as "revision_requested" -- the Policy Engine's revision_requested rule
    # (core.capabilities.policy_engine) is what routes this to Fitness once the
    # graph re-enters Supervisor, not a pending_request transport object.
    assert update["approval_status"] == "revision_requested"

    resumed = graph.invoke(Command(update=update), config)
    # Fitness re-ran (regenerated the plan and re-requested verification/HITL)
    # rather than the run just ending at the point of the revision resume.
    fitness_results = [
        result
        for result in resumed["capability_results"].values()
        if result["capability"] == "fitness"
    ]
    assert len(fitness_results) >= 2
    snapshot = graph.get_state(config)
    assert snapshot.next == ("hitl",)


def test_user_revision_rejected_once_shared_replan_budget_is_exhausted() -> None:
    """A run that already used its one revision must reject a further request
    outright rather than accepting it and looping back into Fitness again."""
    with pytest.raises(ValueError, match="Maximum number of plan revisions"):
        decision_to_resume_update(
            create_approval_decision(
                "revision",
                message="One more change please.",
            ),
            revision_count=MAX_REVISION_COUNT,
        )
