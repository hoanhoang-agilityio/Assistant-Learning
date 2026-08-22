"""Integration checks on what the todo writer actually produces for real requests."""

import pytest

from src.services.todo import FALLBACK_TASKS, MAX_TODO_STEPS, generate_todo
from tests.test_load_context import COMPLETE_PROFILE, PLAN

# Names the writer must never use: the coach agent chooses its own means, and a todo that
# names a tool would decide that for it.
TOOL_NAMES = ("calc_macro", "load_template", "load_exercise", "search_knowledge")

INJURED_PROFILE = COMPLETE_PROFILE | {
    "injuries": [{"body_part": "left shoulder", "status": "ACTIVE"}]
}


@pytest.fixture(scope="module")
async def new_plan_todo(require_openai_key: None) -> list[str]:
    """One live todo for a first-time plan request, reused across the assertions."""
    return await generate_todo(
        "Build me a 4 day fat loss plan I can do at home.", COMPLETE_PROFILE, None
    )


@pytest.mark.integration
async def test_a_request_produces_a_workable_number_of_steps(new_plan_todo) -> None:
    """Too few is not a plan of work; too many spends the turn on planning it."""
    assert 3 <= len(new_plan_todo) <= MAX_TODO_STEPS


@pytest.mark.integration
async def test_the_steps_are_tailored_rather_than_the_fallback(new_plan_todo) -> None:
    """A live writer that returns the fallback means the call silently failed."""
    assert new_plan_todo != list(FALLBACK_TASKS)


@pytest.mark.integration
async def test_the_steps_never_name_a_tool(new_plan_todo) -> None:
    """Which tool answers a step is the coach agent's decision, not the planner's."""
    text = " ".join(new_plan_todo).lower()

    assert not [name for name in TOOL_NAMES if name in text]


@pytest.mark.integration
async def test_an_injury_reaches_the_steps(require_openai_key: None) -> None:
    """A constraint the writer ignores is one the coach agent never hears about."""
    todo = await generate_todo("Build me a 4 day plan.", INJURED_PROFILE, None)

    assert "shoulder" in " ".join(todo).lower()


@pytest.mark.integration
async def test_a_revision_request_is_scoped_to_the_change(
    require_openai_key: None,
) -> None:
    """With a plan on record the user wants it changed, not replaced."""
    todo = await generate_todo(
        "Swap leg day for something easier on my knees.", COMPLETE_PROFILE, PLAN
    )

    assert "knee" in " ".join(todo).lower()
