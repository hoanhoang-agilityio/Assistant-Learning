import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.config.settings import get_settings
from core.graph.run import create_initial_state
from core.subgraphs.fitness.graph import build_fitness_subgraph
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.verification.agent import VerificationAgent
from core.subgraphs.verification.graph import (
    build_verification_subgraph,
    invoke_verification_subgraph,
)
from core.subgraphs.verification.state import VerificationState
from core.subgraphs.verification.utils import (
    FAITHFULNESS_PASS_THRESHOLD,
    citation_check_data,
    consistency_check_data,
    heuristic_faithfulness_data,
    load_verification_context,
    safety_check_data,
)
from core.vfs import VFS
from tests.helpers.planning import seed_execution_plan


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "target_weight_kg": 75.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
    }


@pytest.fixture
def verification_state(
    workspace_root: Path,
    complete_profile: dict[str, Any],
) -> VerificationState:
    initial = create_initial_state(
        run_id="verify-run",
        thread_id="verify-thread",
        query="I want to lose weight with strength training.",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    seed_execution_plan(initial["workspace_path"], complete_profile)
    vfs = VFS.for_run(Path(initial["workspace_path"]))
    evidence = [
        {
            "document_id": "doc_0",
            "url": "https://example.edu/fitness-training",
            "content": "hypertrophy training evidence for strength programming",
            "provider": "tavily",
        }
    ]
    vfs.write(
        "research/sources.json",
        json.dumps(
            [
                {
                    "source_id": "src_0",
                    "title": "Hypertrophy training evidence",
                    "url": "https://example.edu/fitness-training",
                    "snippet": "hypertrophy training evidence",
                    "score": 0.92,
                    "provider": "tavily",
                }
            ]
        ),
    )
    vfs.write(
        "research/findings.json",
        json.dumps(
            {
                "evidence": evidence,
                "evidence_summary": "hypertrophy training evidence collected",
                "source_count": 1,
            }
        ),
    )

    fitness_state = FitnessState(
        workspace_path=initial["workspace_path"],
        profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        execution_plan={},
        structured_findings=None,
        evidence_summary="hypertrophy training evidence collected",
        verification_feedback=None,
        macro_targets={},
        training_constraints={},
        structured_workout=None,
        safety_result={"passed": False, "feedback": []},
        planner_feedback=[],
        planner_attempts=0,
        max_planner_attempts=get_settings().max_planner_attempts,
        is_verification_rerun=False,
        draft_plan=None,
    )
    build_fitness_subgraph().invoke(fitness_state)

    return VerificationState(
        workspace_path=initial["workspace_path"],
        draft_plan="",
        sources=[],
        evidence=[],
        macro_targets={},
        training_plan={},
        safety_flags=[],
        verification_report={},
        faithfulness_score=None,
    )


def test_citation_check_passes_with_evidence_section(verification_state: VerificationState) -> None:
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    draft_plan = vfs.read("fitness/final_plan.md")
    sources = json.loads(vfs.read("research/sources.json"))
    result = citation_check_data(draft_plan, sources)
    assert result["passed"] is True


def test_citation_check_fails_on_zero_sources(verification_state: VerificationState) -> None:
    """Regression (PR7): zero sources gathered is a real grounding failure, not
    "nothing to check" -- `not sources` used to make `passed` unconditionally
    True here, silently rubber-stamping a plan built on zero research evidence."""
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    draft_plan = vfs.read("fitness/final_plan.md")

    result = citation_check_data(draft_plan, [])

    assert result["passed"] is False
    assert "no_sources_gathered" in result["issues"]
    assert result["cited_source_count"] == 0


def test_citation_check_does_not_rubber_stamp_via_evidence_keyword() -> None:
    """Regression (PR7): a draft that mentions "evidence"/"research" (every real
    draft does, via its "## Evidence Summary" section) must not count as citing
    a source that was never actually referenced by URL or title."""
    draft_plan = (
        "# Fitness Plan Draft\n\n"
        "## Training Plan\n\n### Day 1\n- Squat: 3 x 8\n\n"
        "## Evidence Summary\n\n"
        "General hypertrophy and research-backed training guidance was applied.\n"
    )
    sources = [
        {
            "source_id": "src_0",
            "title": "Completely unrelated source title",
            "url": "https://example.edu/never-mentioned",
            "provider": "tavily",
        }
    ]

    result = citation_check_data(draft_plan, sources)

    assert result["passed"] is False
    assert result["cited_source_count"] == 0
    assert "no_sources_referenced_in_draft" in result["issues"]


def test_consistency_check_validates_macro_and_day_count(
    verification_state: VerificationState,
) -> None:
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    draft_plan = vfs.read("fitness/final_plan.md")
    calculations = json.loads(vfs.read("fitness/calculations.json"))
    result = consistency_check_data(
        draft_plan,
        calculations["macro_targets"],
        calculations["training_plan_summary"],
    )
    assert result["passed"] is True


def test_safety_check_fails_on_critical_flags() -> None:
    result = safety_check_data("Plan draft", ["calories_below_safe_minimum"])
    assert result["passed"] is False
    assert "calories_below_safe_minimum" in result["issues"]


def test_safety_check_ignores_unsafe_word_in_evidence_sections() -> None:
    draft = (
        "# Fitness Plan Draft\n\n"
        "## Macro Targets\n\n- Calories: 2200 kcal\n\n"
        "## Training Plan\n\n### Day 1\n- Squat: 3 x 8\n\n"
        "## Evidence Summary\n\n"
        "Weight-loss targets above 1.0 kg/week are usually unrealistic or unsafe.\n\n"
        "## Verification Feedback Applied\n\n"
        "Safety issues: unsafe_language:unsafe\n"
    )
    result = safety_check_data(draft, [])
    assert result["passed"] is True
    assert "unsafe_language:unsafe" not in result["issues"]


def test_safety_check_fails_when_fitness_safety_check_failed_outside_allowlist() -> None:
    """Regression (PR7): the core bug this PR closes. Fitness's own
    validate_workout_safety_data can fail for reasons outside the 4-item
    CRITICAL_SAFETY_FLAGS allowlist (equipment mismatch, duplicate exercise,
    invalid set count, wrong day count, ...) -- previously that failure was
    never persisted anywhere, so Verification's safety gate passed regardless.
    A flag not in the allowlist, combined with the real fitness_safety_passed
    boolean, must now still fail the check."""
    result = safety_check_data(
        "Plan draft",
        ["duplicate_exercise:Day 1:squat"],  # not in CRITICAL_SAFETY_FLAGS
        fitness_safety_passed=False,
    )

    assert result["passed"] is False
    assert "fitness_safety_check_failed" in result["issues"]


def test_safety_check_passes_when_fitness_safety_passed_is_true_and_no_other_issues() -> None:
    """A genuinely passing fitness safety result, with no critical flags and no
    unsafe language in the draft, must still pass."""
    result = safety_check_data("Plan draft", [], fitness_safety_passed=True)

    assert result["passed"] is True
    assert result["issues"] == []


def test_write_fitness_artifacts_persists_safety_passed_boolean(tmp_path) -> None:
    """Regression (PR7): validate_workout_safety_data's passed boolean must be
    persisted, not just its feedback strings, so Verification can read the
    real outcome directly instead of re-deriving an incomplete one."""
    from core.subgraphs.fitness.utils import write_fitness_artifacts
    from tests.helpers.fitness import default_structured_workout

    workspace_path = str(tmp_path / "safety-persist-workspace")
    profile = {"goal": "muscle_gain", "days_per_week": 3, "equipment": "gym"}
    structured_workout = default_structured_workout(profile, {"days_per_week": 3}).model_dump()

    write_fitness_artifacts(
        workspace_path=workspace_path,
        macro_targets={"calories": 2200},
        structured_workout=structured_workout,
        draft_plan="# Draft",
        safety_result={"passed": False, "feedback": ["duplicate_exercise:Day 1:squat"]},
    )

    vfs = VFS.for_run(Path(workspace_path))
    assert vfs.exists("fitness/safety_passed.json")
    assert json.loads(vfs.read("fitness/safety_passed.json")) is False


def test_load_verification_context_reads_fitness_safety_passed(tmp_path) -> None:
    """Regression (PR7): load_verification_context must surface the persisted
    boolean so safety_check_data can use it as the authoritative signal."""
    workspace_path = str(tmp_path / "safety-context-workspace")
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("fitness/safety_passed.json", json.dumps(False))

    context = load_verification_context(workspace_path)

    assert context["fitness_safety_passed"] is False


def test_load_verification_context_defaults_fitness_safety_passed_to_none_when_absent(
    tmp_path,
) -> None:
    """An older workspace predating this field (or one where fitness hasn't run
    yet) must not be mistaken for an explicit pass or fail."""
    workspace_path = str(tmp_path / "no-safety-artifact-workspace")

    context = load_verification_context(workspace_path)

    assert context["fitness_safety_passed"] is None


def test_ragas_faithfulness_meets_threshold(verification_state: VerificationState) -> None:
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    draft_plan = vfs.read("fitness/final_plan.md")
    findings = json.loads(vfs.read("research/findings.json"))
    result = heuristic_faithfulness_data(draft_plan, findings["evidence"])
    assert result["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD
    assert result["pass_fail"] is True


def test_verification_subgraph_writes_vfs_artifacts(verification_state: VerificationState) -> None:
    graph = build_verification_subgraph()
    result = graph.invoke(verification_state)
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    assert vfs.exists("verify/verification_v1.json")
    assert vfs.exists("verify/ragas.json")
    report = json.loads(vfs.read("verify/verification_v1.json"))
    ragas = json.loads(vfs.read("verify/ragas.json"))
    assert report["passed"] is True
    assert result["verification_report"]["ragas"]["pass_fail"] is True
    assert ragas["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD


def test_verification_subgraph_fails_safety_for_flag_outside_allowlist(
    verification_state: VerificationState,
) -> None:
    """Regression (PR7), end-to-end: the compiled verification subgraph --
    load_context -> safety_check, not safety_check_data called in isolation --
    must read fitness's persisted passed boolean and fail the safety gate for
    a flag outside CRITICAL_SAFETY_FLAGS (e.g. a duplicate exercise), which
    previously passed silently regardless of what fitness actually found."""
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    vfs.write("fitness/safety_flags.json", json.dumps(["duplicate_exercise:Day 1:squat"]))
    vfs.write("fitness/safety_passed.json", json.dumps(False))

    graph = build_verification_subgraph()
    result = graph.invoke(verification_state)

    safety_result = result["verification_report"]["safety"]
    assert safety_result["passed"] is False
    assert "fitness_safety_check_failed" in safety_result["issues"]


def test_verification_agent_returns_structured_report(
    verification_state: VerificationState,
    complete_profile: dict[str, Any],
) -> None:
    orchestration_state: OrchestrationState = {
        "run_id": "verify-run",
        "thread_id": "verify-thread",
        "current_node": "fitness",
        "query": "lose weight",
        "user_profile": complete_profile,
        "constraints": {"days_per_week": 3},
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "route_decision": None,
        "retry_count": 0,
        "replan_count": 0,
        "verification_passed": False,
        "faithfulness_score": None,
        "waiting_for_user": False,
        "approval_status": None,
        "user_response": None,
        "workspace_path": verification_state["workspace_path"],
        "final_artifact_path": None,
    }
    updates = VerificationAgent().run(orchestration_state)
    assert updates["current_node"] == "verification"
    assert updates["verification_passed"] is True
    assert updates["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD


def test_invoke_verification_subgraph_marks_failure_without_draft(workspace_root: Path) -> None:
    initial = create_initial_state(
        run_id="verify-fail",
        thread_id="verify-fail-thread",
        query="test",
        workspace_root=workspace_root,
    )
    orchestration_state: OrchestrationState = {
        **initial,
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
    }
    updates = invoke_verification_subgraph(orchestration_state)
    assert updates["verification_passed"] is False
    assert updates["faithfulness_score"] is not None
