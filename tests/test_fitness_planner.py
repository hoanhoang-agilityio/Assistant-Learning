from typing import Any

import pytest

from core.capabilities.fitness import planner as planner_module
from core.capabilities.fitness.planner import (
    build_planner_context_payload,
    build_planner_feedback_payload,
    build_planner_payload,
    configure_fitness_planner,
    generate_structured_workout,
)
from core.capabilities.research.schema import ResearchFindings
from core.llm.payload import compact_json
from core.planning.schema import ExecutionPlan, PlanTask
from tests.helpers.fitness import default_structured_workout


@pytest.fixture(autouse=True)
def reset_fitness_planner_override() -> None:
    configure_fitness_planner(None)
    yield
    configure_fitness_planner(None)


@pytest.fixture
def sample_execution_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale="Research-backed fat loss plan with strength emphasis.",
        tasks=[
            PlanTask(
                order=1,
                task="Research evidence-based fat loss training volume",
                rationale="Volume must align with evidence for sustainable fat loss.",
            ),
            PlanTask(
                order=2,
                task="Gather equipment-specific exercise substitutions",
                rationale="User constraints require practical exercise swaps.",
            ),
            PlanTask(
                order=3,
                task="Verify source credibility for training recommendations",
                rationale="Downstream synthesis must rely on trustworthy evidence.",
            ),
        ],
        plan_markdown="# Plan\n\nFat loss with gym equipment and 3 training days per week.\n",
    )


@pytest.fixture
def sample_findings() -> ResearchFindings:
    return ResearchFindings(
        consensus="10-20 weekly sets per muscle group supports hypertrophy during fat loss phases.",
        key_findings=[
            {
                "claim": "Full-body or upper/lower splits work well for 3-day schedules.",
                "source_url": "https://example.com/hypertrophy",
            },
            {
                "claim": "Avoid overhead pressing with shoulder pain.",
                "source_url": "https://example.com/hypertrophy",
            },
        ],
        limitations=["Limited sport-specific data"],
        conflicting_evidence=[],
        recommended_sources=["https://example.com/hypertrophy"],
    )


def test_build_planner_payload_includes_feedback_and_findings(
    sample_execution_plan: ExecutionPlan,
    sample_findings: ResearchFindings,
) -> None:
    payload = build_planner_payload(
        profile={"goal": "fat_loss"},
        constraints={"days_per_week": 3, "equipment": "gym"},
        macro_targets={"calories": 2200},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=sample_execution_plan,
        structured_findings=sample_findings,
        planner_feedback=["training_day_count_mismatch:expected_3_got_4"],
        verification_feedback="Increase weekly volume slightly.",
    )
    assert payload["execution_plan"]["plan_rationale"]
    assert "plan_markdown" not in payload["execution_plan"]
    assert "constraints" not in payload
    assert payload["structured_findings"]["consensus"]
    assert payload["planner_feedback"] == ["training_day_count_mismatch:expected_3_got_4"]
    assert payload["verification_feedback"] == "Increase weekly volume slightly."


def test_build_planner_payload_without_execution_plan_does_not_raise(
    sample_findings: ResearchFindings,
) -> None:
    """Regression test: Fitness reached directly from a build_plan intent with no prior
    Planning/Research hop (no plan/execution_plan.json in the run workspace) must not crash
    -- `load_fitness_context` passes None through, not a fake {} plan lacking "tasks"."""
    payload = build_planner_payload(
        profile={"goal": "fat_loss"},
        constraints={"days_per_week": 3, "equipment": "gym"},
        macro_targets={"calories": 2200},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=None,
        structured_findings=sample_findings,
        planner_feedback=[],
        verification_feedback=None,
    )
    assert payload["execution_plan"] is None


def test_generate_structured_workout_uses_override(
    sample_execution_plan: ExecutionPlan,
    sample_findings: ResearchFindings,
) -> None:
    captured: dict[str, Any] = {}

    def override(**kwargs: Any):
        captured.update(kwargs)
        return default_structured_workout(kwargs["profile"], kwargs["constraints"])

    configure_fitness_planner(override)
    workout = generate_structured_workout(
        profile={"goal": "fat_loss", "days_per_week": 3},
        constraints={"days_per_week": 3, "equipment": "gym"},
        macro_targets={"calories": 2200},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=sample_execution_plan,
        structured_findings=sample_findings,
        planner_feedback=[],
        verification_feedback=None,
    )
    assert workout.split.startswith("3-day")
    assert len(workout.days) == 3
    assert captured["structured_findings"] == sample_findings


def test_planner_context_payload_includes_evidence_snippets(
    sample_execution_plan: ExecutionPlan,
    sample_findings: ResearchFindings,
) -> None:
    context = build_planner_context_payload(
        profile={"goal": "fat_loss"},
        macro_targets={"calories": 2200},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=sample_execution_plan,
        structured_findings=sample_findings,
        evidence=[
            {
                "url": "https://example.com/hypertrophy",
                "content": "Full-body splits work well for 3-day schedules.",
            }
        ],
    )
    assert context["evidence_snippets"][0]["url"] == "https://example.com/hypertrophy"
    assert context["structured_findings"]["key_findings"][0]["source_url"]
    assert "recommended_sources" in context["structured_findings"]
    assert "planner_feedback" not in context
    assert "verification_feedback" not in context


def test_generate_structured_workout_reuses_stable_prefix_across_retry(
    sample_execution_plan: ExecutionPlan,
    sample_findings: ResearchFindings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry (feedback changes, context doesn't) must send a byte-identical
    leading JSON block so OpenAI's prompt caching has a real prefix to hit."""
    captured_contents: list[str] = []

    def fake_invoke(_schema, messages, **_kwargs):
        captured_contents.append(messages[-1].content)
        return default_structured_workout({"goal": "fat_loss"}, {"days_per_week": 3})

    monkeypatch.setattr(planner_module, "invoke_standard_structured_output", fake_invoke)

    common_kwargs = dict(
        profile={"goal": "fat_loss"},
        constraints={"days_per_week": 3, "equipment": "gym"},
        macro_targets={"calories": 2200},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        execution_plan=sample_execution_plan,
        structured_findings=sample_findings,
    )
    generate_structured_workout(**common_kwargs, planner_feedback=[], verification_feedback=None)
    generate_structured_workout(
        **common_kwargs,
        planner_feedback=["training_day_count_mismatch:expected_3_got_4"],
        verification_feedback="Increase weekly volume slightly.",
    )

    assert len(captured_contents) == 2
    first_context_block, _, _ = captured_contents[0].partition("\n")
    second_context_block, _, _ = captured_contents[1].partition("\n")
    assert first_context_block == second_context_block
    assert captured_contents[0] != captured_contents[1]

    expected_context_block = compact_json(
        build_planner_context_payload(
            profile=common_kwargs["profile"],
            macro_targets=common_kwargs["macro_targets"],
            training_constraints=common_kwargs["training_constraints"],
            execution_plan=common_kwargs["execution_plan"],
            structured_findings=common_kwargs["structured_findings"],
        )
    )
    assert first_context_block == expected_context_block


def test_build_planner_feedback_payload_includes_revision_feedback_when_present() -> None:
    payload = build_planner_feedback_payload(
        planner_feedback=["dup", "dup", "real issue"],
        verification_feedback=None,
        revision_feedback="  tighten the split  ",
    )
    assert payload["planner_feedback"] == ["dup", "real issue"]
    assert payload["revision_feedback"] == "tighten the split"
    assert "verification_feedback" not in payload or payload["verification_feedback"] is None
