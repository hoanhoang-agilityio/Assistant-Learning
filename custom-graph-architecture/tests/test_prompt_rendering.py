"""Tests for how state values are rendered into the data blocks a prompt carries."""

import json

from src.prompts.rendering import as_prompt_json
from tests.test_load_user_context import COMPLETE_PROFILE, PLAN


def test_the_value_survives_the_rendering() -> None:
    """Compactness that changed the data would buy tokens by lying to the model."""
    assert json.loads(as_prompt_json(COMPLETE_PROFILE)) == json.loads(
        json.dumps(COMPLETE_PROFILE, default=str)
    )


def test_nothing_is_spent_on_whitespace() -> None:
    """An indented block costs about a third more tokens for the same data, on every retry."""
    rendered = as_prompt_json(PLAN)

    assert "\n" not in rendered
    assert ", " not in rendered
    assert ": " not in rendered


def test_the_rendering_is_stable() -> None:
    """An unstable key order makes two identical turns two different prompts to cache."""
    assert as_prompt_json(COMPLETE_PROFILE) == as_prompt_json(
        dict(reversed(list(COMPLETE_PROFILE.items())))
    )


def test_what_cannot_be_serialised_is_rendered_rather_than_raising() -> None:
    """A raising prompt builder loses the turn over a field the model barely reads."""
    assert as_prompt_json({"seen_at": object()})


def test_nothing_to_render_reads_as_nothing() -> None:
    """The caller substitutes its own wording for an absent profile or plan."""
    assert as_prompt_json(None) is None
    assert as_prompt_json({}) is None
    assert as_prompt_json([]) is None
