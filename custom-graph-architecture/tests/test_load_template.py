"""Tests for the ``load_template`` tool and the template selection behind it."""

import json
from pathlib import Path

import pytest

from src.core.langgraph.tools import COACH_TOOLS, load_template
from src.core.langgraph.tools.load_template import NO_TEMPLATE, clamp_training_days
from src.schemas import FitnessGoal, WorkoutTemplate
from src.services import catalogue

DATA_DIR = Path("data")


@pytest.fixture(scope="module")
def templates() -> list[WorkoutTemplate]:
    """The seeded templates, as the tool hands them to the agent."""
    rows = json.loads((DATA_DIR / "templates.json").read_text())
    return [WorkoutTemplate.model_validate(row) for row in rows]


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch, templates):
    """Serve the seed files in place of Postgres, filtering on goal as the query does."""

    def _serve(subset: list[WorkoutTemplate] | None = None) -> None:
        available = templates if subset is None else subset

        async def _fetch(goal: FitnessGoal) -> list[WorkoutTemplate]:
            matching = [template for template in available if goal in template.goals]
            return matching or available

        monkeypatch.setattr(catalogue, "fetch_templates", _fetch)

    return _serve


# --- Ranking ------------------------------------------------------------------------------


def test_the_template_training_the_requested_week_wins(templates) -> None:
    """A user who can train three days should not be handed a five-day split."""
    best = catalogue.rank_templates(templates, 3)[0]

    assert best.days_per_week == 3


def test_popularity_breaks_a_tie(templates) -> None:
    """Two templates train three days a week; the ranking has to choose between them."""
    best = catalogue.rank_templates(templates, 3)[0]

    assert best.id == "full_body_3day"


def test_the_ends_of_the_range_have_a_template_of_their_own(templates) -> None:
    """A once-a-week user used to be handed two days, a six-day user five."""
    assert catalogue.rank_templates(templates, 1)[0].days_per_week == 1
    assert catalogue.rank_templates(templates, 6)[0].days_per_week == 6
    assert catalogue.rank_templates(templates, 7)[0].days_per_week == 7


def test_an_unavailable_week_falls_back_to_the_closest_one(templates) -> None:
    """The goal filter runs first, so the week the user asked for can be missing."""
    available = [template for template in templates if template.days_per_week != 3]

    best = catalogue.rank_templates(available, 3)[0]

    assert best.days_per_week == 4


def test_ranking_is_total_so_the_same_request_returns_the_same_template(
    templates,
) -> None:
    """The gate re-resolves the plan by `template_id`; an unstable pick is a flaky plan."""
    first = [template.id for template in catalogue.rank_templates(templates, 4)]
    second = [
        template.id
        for template in catalogue.rank_templates(list(reversed(templates)), 4)
    ]

    assert first == second


def test_nothing_to_rank_ranks_to_nothing() -> None:
    """An empty catalogue is the case `find_template` turns into the tool's error."""
    assert catalogue.rank_templates([], 3) == []


# --- Selection ----------------------------------------------------------------------------


async def test_the_goal_is_selected_on_before_the_week_is(seeded, templates) -> None:
    """A template is only a reasonable choice for the goals it lists."""
    seeded()

    template = await catalogue.find_template(FitnessGoal.GENERAL_FITNESS, 4)

    assert FitnessGoal.GENERAL_FITNESS in template.goals


async def test_a_goal_no_template_covers_still_returns_a_week(seeded) -> None:
    """`STRENGTH` has no template of its own, and a strength user still has to train."""
    seeded()

    template = await catalogue.find_template(FitnessGoal.STRENGTH, 4)

    assert template is not None
    assert template.days_per_week == 4


async def test_an_empty_catalogue_selects_nothing(seeded) -> None:
    """Before the seed has been loaded there is genuinely no answer to give."""
    seeded([])

    assert await catalogue.find_template(FitnessGoal.FAT_LOSS, 4) is None


async def test_an_unreachable_database_selects_nothing_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising tool aborts the agent's turn; an empty one lets it carry on."""

    async def _explode(goal: FitnessGoal) -> list[WorkoutTemplate]:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(catalogue, "fetch_templates", _explode)

    assert await catalogue.find_template(FitnessGoal.FAT_LOSS, 4) is None


# --- The tool -----------------------------------------------------------------------------


async def test_the_tool_returns_the_template_the_agent_has_to_fill(seeded) -> None:
    """The agent needs the slots and their prescribed volume, not just an id."""
    seeded()

    result = await load_template.ainvoke(
        {"goal": FitnessGoal.FAT_LOSS, "days_per_week": 4}
    )

    assert result["id"] == "upper_lower_4day"
    assert result["training_days"][0]["exercise_slots"]


async def test_the_tool_returns_json_the_agent_can_read(seeded) -> None:
    """Enums left as objects reach the model as `MovementPattern.HORIZONTAL_PUSH`."""
    seeded()

    result = await load_template.ainvoke(
        {"goal": FitnessGoal.FAT_LOSS, "days_per_week": 4}
    )

    assert json.dumps(result)


async def test_an_impossible_week_is_clamped_rather_than_refused(seeded) -> None:
    """A model that passes 0 or 99 days should still get the nearest real template."""
    seeded()

    result = await load_template.ainvoke(
        {"goal": FitnessGoal.FAT_LOSS, "days_per_week": 99}
    )

    assert result["training_days"]
    assert clamp_training_days(0) == 1
    assert clamp_training_days(99) == 7


async def test_no_template_is_said_in_words(seeded) -> None:
    """`{}` reads to the agent as a template with no days, and it would prescribe none."""
    seeded([])

    result = await load_template.ainvoke(
        {"goal": FitnessGoal.FAT_LOSS, "days_per_week": 4}
    )

    assert result == {"error": NO_TEMPLATE}


# --- Binding ------------------------------------------------------------------------------


def test_the_tool_is_bound_to_the_coach_agent() -> None:
    """Written but unbound, the agent would invent a template instead of looking one up."""
    assert load_template in COACH_TOOLS


def test_the_tool_describes_its_arguments_to_the_model() -> None:
    """The model picks the arguments; an untyped goal would arrive as free text."""
    schema = load_template.args_schema.model_json_schema()

    assert set(schema["properties"]) == {"goal", "days_per_week"}


# --- Against the seeded table ---------------------------------------------------------------


@pytest.mark.integration
async def test_the_goal_filter_runs_in_the_database(require_postgres: None) -> None:
    """`goals` is a JSONB document, so the filter is containment and not equality."""
    matching = await catalogue.fetch_templates(FitnessGoal.GENERAL_FITNESS)

    assert {template.id for template in matching} == {
        "full_body_1day",
        "full_body_3day",
        "upper_lower_2day",
    }


@pytest.mark.integration
async def test_a_seeded_lookup_returns_a_whole_template(require_postgres: None) -> None:
    """The row rebuilds into the domain model the agent is handed."""
    template = await catalogue.find_template(FitnessGoal.MUSCLE_GAIN, 5)

    assert template.id == "chest_back_legs_upper_lower_5day"
    assert len(template.training_days) == 5
