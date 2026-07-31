from pathlib import Path

from langgraph.types import Command

from core.orchestration.graph.builder import build_graph
from core.orchestration.hitl.resume import (
    create_approval_decision,
    decision_to_resume_update,
)
from core.orchestration.hitl.utils import request_approval_data
from core.shared.profile.extraction import configure_profile_extractor
from core.shared.profile.schema import ExtractedProfile
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
    # Revisions now route through User -> Planning -> Fitness (see policy_engine's
    # revision_requested rule), so User's apply_revision_overrides re-extracts the
    # revision text via the profile extractor -- must be stubbed like every other
    # test that exercises the User subgraph, or this makes a real LLM call.
    configure_profile_extractor(lambda _query: ExtractedProfile())
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
    # (core.orchestration.routing.policy_engine) is what routes this to Fitness once the
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

    # Revisions are uncapped (supervisor_max_hops is the only backstop) -- a
    # *second* revision request against the same run must also succeed, not be
    # rejected as over-budget.
    second_update = decision_to_resume_update(
        create_approval_decision(
            "revision",
            message="Also make the last day focus on upper body.",
        ),
        revision_count=resumed["revision_count"],
    )
    assert second_update["revision_count"] == 2

    twice_resumed = graph.invoke(Command(update=second_update), config)
    fitness_results_after_second_revision = [
        result
        for result in twice_resumed["capability_results"].values()
        if result["capability"] == "fitness"
    ]
    assert len(fitness_results_after_second_revision) > len(fitness_results)
    snapshot = graph.get_state(config)
    assert snapshot.next == ("hitl",)
