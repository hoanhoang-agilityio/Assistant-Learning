import time

from core.graph.run import create_initial_state
from core.graph.service import RunOrchestrator
from core.profile.extraction import configure_profile_extractor
from core.profile.schema import ExtractedProfile, Goal, Profile
from core.subgraphs.planning.utils import profile_to_orchestration_updates
from core.subgraphs.user.utils import extract_profile


def test_resume_clarification_merges_user_response_into_profile(
    memory_checkpointer,
    tmp_path,
) -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(age=28, sex="male", height_cm=175, current_weight_kg=85),
            goal=Goal(goal="fat_loss", target_weight_kg=75),
        )
    )
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    initial = create_initial_state(
        run_id="clarify-run",
        thread_id="clarify-run",
        query="I want to lose weight.",
        workspace_root=tmp_path / "workspace",
    )
    config = {"configurable": {"thread_id": initial["thread_id"]}}
    orchestrator.graph.invoke(
        {
            **initial,
            "request_type": "fat_loss",
            "affected_domains": ["planning", "research", "fitness", "verify"],
            "waiting_for_user": True,
            "user_profile": {
                "goal": "fat_loss",
                "activity_level": "gym_3x_week",
                "missing_fields": ["age", "target_weight_kg"],
            },
        },
        config,
    )
    snapshot = orchestrator.graph.get_state(config)
    original_query = snapshot.values["query"]
    user_response = "Male, 28 years old, 175 cm, 85 kg. Goal: 75 kg"
    cleared_profile = {
        key: value
        for key, value in snapshot.values.get("user_profile", {}).items()
        if key != "missing_fields"
    }
    clarification = extract_profile(
        query=user_response,
        user_profile=cleared_profile,
        constraints={"days_per_week": 3},
    )
    sync = profile_to_orchestration_updates(clarification)
    update = {
        "user_response": user_response,
        "approval_status": "revision_requested",
        "waiting_for_user": False,
        "user_profile": sync["user_profile"],
        "constraints": {
            **(snapshot.values.get("constraints") or {}),
            **sync["constraints"],
        },
    }
    orchestrator._execute_resume_run(initial["run_id"], update, config)

    checkpoint = orchestrator.graph.get_state(config)
    values = checkpoint.values
    assert values["query"] == original_query
    assert values["user_profile"]["age"] == 28
    assert values["user_profile"]["target_weight_kg"] == 75.0
    assert not values["user_profile"].get("missing_fields")


def test_resume_run_profile_form_via_command_resume(
    memory_checkpointer,
    tmp_path,
) -> None:
    """A run with an incomplete profile pauses inside the User subgraph (interrupt());
    resume_run's new form_data path resumes it via Command(resume=...), not
    Command(update=...), and the profile ends up complete/valid."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    run_status = orchestrator.create_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    assert run_status.status == "waiting_hitl"
    assert run_status.hitl_type == "profile_form"

    orchestrator.resume_run(
        run_status.run_id,
        form_data={
            "sex": "male",
            "current_weight_kg": 85.0,
            "target_weight_kg": 75.0,
            "goal": "fat_loss",
        },
    )

    config = {"configurable": {"thread_id": run_status.run_id}}
    snapshot = orchestrator.graph.get_state(config)
    for _ in range(100):
        if snapshot.next != ("user",):
            break
        time.sleep(0.02)
        snapshot = orchestrator.graph.get_state(config)
    else:
        raise AssertionError("profile form resume did not complete in time")

    assert snapshot.values["profile_complete"] is True
    assert snapshot.values["profile_valid"] is True
    assert snapshot.values["user_profile"]["sex"] == "male"
    assert snapshot.values["user_profile"]["current_weight_kg"] == 85.0


def test_get_run_reports_running_while_pending_resume_race_leaves_stale_checkpoint(
    memory_checkpointer,
) -> None:
    """A background resume thread (start_resume_run/start_profile_form_resume/etc.) can
    have a run_id in _pending_runs before its Command(...) invoke has written a single
    checkpoint update -- get_run() must not mistake that untouched, pre-resume checkpoint
    (still showing the old interrupt) for a genuinely settled outcome, or a poller resuming
    the profile form would see the exact same "still needs the form" state it just
    submitted and stop polling before the real result ever arrives."""
    configure_profile_extractor(lambda _query: ExtractedProfile())
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    run_status = orchestrator.create_run(
        query="I want a 4-day training plan to lose weight.",
        user_profile={"age": 30, "height_cm": 175},
        constraints={"days_per_week": 4, "equipment": "gym"},
    )
    assert run_status.status == "waiting_hitl"
    assert run_status.hitl_type == "profile_form"

    # Simulate the race window: a resume thread has been registered as pending, but hasn't
    # advanced the checkpoint past the pre-resume interrupt yet.
    with orchestrator._lock:
        orchestrator._pending_runs[run_status.run_id] = {}
    raced_status = orchestrator.get_run(run_status.run_id)
    assert raced_status.status == "running"

    # Once the (simulated) background thread finishes and clears the pending marker, the
    # real checkpoint state -- still genuinely paused, since nothing actually resumed it --
    # must be reported again rather than staying stuck on "running" forever.
    with orchestrator._lock:
        orchestrator._pending_runs.pop(run_status.run_id, None)
    settled_status = orchestrator.get_run(run_status.run_id)
    assert settled_status.status == "waiting_hitl"
    assert settled_status.hitl_type == "profile_form"


def _waiting_for_approval_state(run_id: str, tmp_path) -> dict:
    initial = create_initial_state(
        run_id=run_id,
        thread_id=run_id,
        query="Approve my plan",
        workspace_root=tmp_path / run_id,
    )
    return {
        **initial,
        "request_type": "training_plan",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "current_node": "supervisor",
        "verification_passed": True,
        "route_decision": "COMPLETE",
        "waiting_for_user": True,
        "approval_status": "pending",
        "profile_complete": True,
        "profile_valid": True,
    }


def test_resume_run_free_text_approval_uses_strict_classification(
    memory_checkpointer,
    tmp_path,
) -> None:
    """resume_run's free-text approval path (no decision_type) classifies user_response with
    classify_approval_response(strict=True) -- only exact "approve"/"approved"/"yes" (and
    reject equivalents) match; prefix phrasing like "approving this" does not. This is the
    pre-existing behavior of the now-deleted `_approval_from_response`, preserved by the
    `strict` parameter rather than unified with hitl_control_data's permissive prefix-matching
    rule (which stays exercised separately by tests/test_partial_rerun.py)."""
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)

    exact_config = {"configurable": {"thread_id": "approve-exact"}}
    orchestrator.graph.invoke(_waiting_for_approval_state("approve-exact", tmp_path), exact_config)
    exact_status = orchestrator.resume_run("approve-exact", user_response="approve")
    assert exact_status.approval_status == "approved"

    # Under strict=True, "approving this plan" doesn't match the exact "approve"/"approved"/
    # "yes" set, so it's classified "revision_requested" -- which resume_run's revision branch
    # then normalizes to route_decision="REPLAN"/approval_status="pending" (see
    # core.hitl.resume.user_revision_to_replan_update). If strict matching regressed to the
    # permissive prefix rule, this input would instead be classified "approved" and skip the
    # revision branch entirely, leaving route_decision untouched at "COMPLETE".
    prefix_config = {"configurable": {"thread_id": "approve-prefix"}}
    orchestrator.graph.invoke(
        _waiting_for_approval_state("approve-prefix", tmp_path), prefix_config
    )
    prefix_status = orchestrator.resume_run("approve-prefix", user_response="approving this plan")
    assert prefix_status.approval_status == "pending"
    assert prefix_status.route_decision == "REPLAN"
