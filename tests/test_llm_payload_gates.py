"""Gate tests: fixture payload measurements and performance budgets."""

from langchain_core.messages import HumanMessage, SystemMessage

from core.adapters.llm.budgets import (
    LLM_NODE_BUDGETS,
    check_payload_budget,
    measure_fixture_baseline,
)
from core.adapters.llm.metrics import estimate_payload_tokens, reset_llm_metrics
from core.adapters.llm.payload import compact_json
from core.capabilities.fitness.planner import build_planner_payload
from core.capabilities.fitness.prompts import FITNESS_PLANNER_SYSTEM_PROMPT
from core.capabilities.research.prompts import (
    QUERY_PLANNING_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)
from core.capabilities.research.schema import ResearchFindings
from core.capabilities.research.utils import (
    build_research_context_payload,
    build_synthesis_llm_extra,
)
from core.shared.planning.schema import ExecutionPlan, PlanTask
from core.shared.profile.extraction import _EXTRACTION_SYSTEM_PROMPT
from core.shared.profile.goal_spec import derive_goal_spec

_MIN_PLAN_MARKDOWN = "# Test Plan\n\nSummary with enough characters for schema validation.\n"
_MIN_PLAN_RATIONALE = "Test plan rationale with enough characters for validation."


def _sample_plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale=_MIN_PLAN_RATIONALE,
        tasks=[
            PlanTask(order=1, task="First research task for testing", rationale="First rationale"),
            PlanTask(
                order=2, task="Second research task for testing", rationale="Second rationale"
            ),
            PlanTask(order=3, task="Third research task for testing", rationale="Third rationale"),
        ],
        plan_markdown=_MIN_PLAN_MARKDOWN,
    )


def test_fixture_measurements_within_budgets() -> None:
    reset_llm_metrics()
    profile = {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85,
        "target_weight_kg": 75,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
        "days_per_week": 3,
        "equipment": "gym",
    }
    query = "I want to lose weight with a gym 3x/week plan."
    goal_spec = derive_goal_spec(profile)
    plan = _sample_plan()
    findings = ResearchFindings(
        consensus="Consensus statement with enough characters for validation.",
        key_findings=[
            {
                "claim": "Finding one with enough detail.",
                "source_url": "https://example.com",
            },
            {
                "claim": "Finding two with enough detail.",
                "source_url": "https://example.com",
            },
        ],
        limitations=["Limited data"],
        conflicting_evidence=[],
        recommended_sources=["https://example.com"],
    )

    cases: list[tuple[str, str, dict | str]] = [
        (
            "profile_extraction",
            _EXTRACTION_SYSTEM_PROMPT,
            query,
        ),
        (
            "research_query_planning",
            QUERY_PLANNING_SYSTEM_PROMPT,
            build_research_context_payload(
                query=query,
                profile=profile,
                goal_spec=goal_spec,
                execution_plan=plan,
            ),
        ),
        (
            "research_synthesis",
            SYNTHESIS_SYSTEM_PROMPT,
            build_research_context_payload(
                query=query,
                profile=profile,
                goal_spec=goal_spec,
                extra=build_synthesis_llm_extra(
                    sources=[
                        {"title": "Source", "url": "https://example.com/other", "snippet": "x"}
                    ],
                    evidence=[{"url": "https://example.com", "content": "Evidence snippet."}],
                ),
            ),
        ),
        (
            "fitness_planner",
            FITNESS_PLANNER_SYSTEM_PROMPT,
            build_planner_payload(
                profile=profile,
                constraints={"days_per_week": 3, "equipment": "gym"},
                macro_targets={
                    "bmr": 1700,
                    "tdee": 2200,
                    "calories": 2000,
                    "protein_g": 160,
                    "carbs_g": 200,
                    "fat_g": 60,
                    "goal": "fat_loss",
                    "activity_level": "gym_3x_week",
                },
                training_constraints={
                    "days_per_week": 3,
                    "equipment": "gym",
                    "goal": "fat_loss",
                },
                execution_plan=plan,
                structured_findings=findings,
                planner_feedback=[],
                verification_feedback=None,
            ),
        ),
    ]

    for node, system_prompt, payload in cases:
        if isinstance(payload, str):
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=payload),
            ]
            measured = estimate_payload_tokens(messages)
        else:
            measured = measure_fixture_baseline(node, system_prompt, payload)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=compact_json(payload)),
            ]
        budget = LLM_NODE_BUDGETS[node]
        assert measured <= budget.max_input_tokens, (
            f"{node}: measured {measured} exceeds budget {budget.max_input_tokens}"
        )
        result = check_payload_budget(node, messages)
        assert result["within_budget"] is True


def test_estimate_payload_tokens_matches_message_list() -> None:
    messages = [
        SystemMessage(content="system"),
        HumanMessage(content=compact_json({"goal": "fat_loss"})),
    ]
    assert estimate_payload_tokens(messages) > 0
