"""Tests for rendering a verified plan as the markdown shown in HITL review."""

import pytest

import src.services.plan_presentation as plan_presentation_module
from src.services.plan_presentation import format_plan_markdown, render_plan_markdown
from tests.test_verification_completeness import CATALOGUE, complete_plan


def test_the_markdown_names_every_exercise_by_its_catalogue_name() -> None:
    """The reviewer sees exercise names, not the ids the plan prescribes by."""
    markdown = format_plan_markdown(complete_plan(), CATALOGUE)

    assert "Barbell bench press" in markdown
    assert "Seated cable row" in markdown
    assert "Barbell back squat" in markdown


def test_the_markdown_carries_the_calorie_and_macro_targets() -> None:
    """The numbers the coach agent set are what the reviewer is approving."""
    markdown = format_plan_markdown(complete_plan(), CATALOGUE)

    assert "2200 kcal" in markdown
    assert "180g protein" in markdown


def test_the_markdown_groups_exercises_under_their_own_day() -> None:
    """Two training days must not collapse into one list."""
    markdown = format_plan_markdown(complete_plan(), CATALOGUE)

    assert "Day 1 — Upper" in markdown
    assert "Day 2 — Lower" in markdown


async def test_rendering_resolves_exercises_from_the_catalogue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The async entry point fetches its own exercises rather than expecting them passed in."""

    async def fetch_exercises_by_id(exercise_ids: list[str]) -> dict:
        return {
            exercise_id: CATALOGUE[exercise_id]
            for exercise_id in exercise_ids
            if exercise_id in CATALOGUE
        }

    monkeypatch.setattr(
        plan_presentation_module, "fetch_exercises_by_id", fetch_exercises_by_id
    )

    markdown = await render_plan_markdown(complete_plan())

    assert "Barbell bench press" in markdown
