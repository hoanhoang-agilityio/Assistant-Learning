"""Tests for the ``check_profile_complete`` node and its routing."""

import pytest

import src.services.memory as memory_service
from src.core.configs.config import settings
from src.core.langgraph.nodes.context import (
    check_profile_complete,
    route_after_profile_check,
)
from src.schemas import initial_state
from src.services.profile import REQUIRED_PROFILE_FIELDS
from tests.test_load_user_context import COMPLETE_PROFILE, USER_ID


def _state(profile: dict | None, revision_fields: list[str] | None = None) -> dict:
    """A state as it stands after ``merge_profile`` merged the current message in."""
    return initial_state("build me a plan", USER_ID) | {
        "profile": profile,
        "revision_fields": revision_fields or [],
    }


async def test_a_user_with_no_profile_is_asked_for_everything() -> None:
    """A first-time user needs the whole required set named, not an empty request."""
    actual_update = await check_profile_complete(_state(None))

    assert actual_update["missing_fields"] == list(REQUIRED_PROFILE_FIELDS)


async def test_only_the_absent_fields_are_named() -> None:
    """Data already stored must not be requested again."""
    partial = {name: COMPLETE_PROFILE[name] for name in ("age", "sex", "height_cm")}

    actual_update = await check_profile_complete(_state(partial))

    assert actual_update["missing_fields"] == [
        "current_weight_kg",
        "activity_level",
        "goal",
        "training_days_per_week",
    ]


@pytest.mark.parametrize("blank", [None, "", "   "])
async def test_a_blank_stored_value_is_still_missing(blank: object) -> None:
    """A field saved as an empty string is an unanswered question, not an answer."""
    actual_update = await check_profile_complete(
        _state(COMPLETE_PROFILE | {"goal": blank})
    )

    assert actual_update["missing_fields"] == ["goal"]


async def test_a_complete_profile_is_marked_complete_and_resets_the_ask_state() -> None:
    """The point of moving this here: this turn's own facts can complete the profile."""
    actual_update = await check_profile_complete(
        _state(COMPLETE_PROFILE) | {"user_info_retry_count": 2}
    )

    assert actual_update == {"missing_fields": [], "user_info_retry_count": 0}


async def test_a_revision_flagged_field_is_treated_as_missing_even_if_optional() -> (
    None
):
    """target_weight_kg is not required, but a flagged-and-cleared one must still be asked for."""
    profile = COMPLETE_PROFILE | {"target_weight_kg": None}

    actual_update = await check_profile_complete(
        _state(profile, revision_fields=["target_weight_kg"])
    )

    assert actual_update["missing_fields"] == ["target_weight_kg"]


async def test_a_revision_field_already_satisfied_by_a_required_field_is_not_duplicated() -> (
    None
):
    """A required field that is also flagged for revision must only be asked for once."""
    actual_update = await check_profile_complete(_state(None, revision_fields=["goal"]))

    assert actual_update["missing_fields"].count("goal") == 1


async def test_the_node_reads_state_and_not_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``merge_profile`` already merged in the store's data; a second read could disagree."""

    async def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("check_profile_complete must not touch long-term memory")

    monkeypatch.setattr(memory_service.graph_runtime, "store", fail)

    actual_update = await check_profile_complete(_state({"age": 34}))

    assert actual_update["missing_fields"] == [
        "sex",
        "height_cm",
        "current_weight_kg",
        "activity_level",
        "goal",
        "training_days_per_week",
    ]


@pytest.mark.parametrize("attempts_made", [0, 1, 2])
async def test_the_user_is_asked_again_while_attempts_remain(
    attempts_made: int,
) -> None:
    """Three questions are allowed before the run gives up on collecting the profile."""
    state = _state(None) | {
        "missing_fields": ["goal"],
        "user_info_retry_count": attempts_made,
    }

    assert route_after_profile_check(state) == "ask"


async def test_the_run_gives_up_once_the_limit_is_reached() -> None:
    """Without this the loop is unbounded: ask, wait, extract, check, ask again."""
    state = _state(None) | {
        "missing_fields": ["goal"],
        "user_info_retry_count": settings.USER_INFO_MAX_RETRIES,
    }

    assert route_after_profile_check(state) == "exhausted"


async def test_a_count_beyond_the_limit_still_gives_up() -> None:
    """A resumed checkpoint could carry a count past the boundary; it must not reopen."""
    state = _state(None) | {
        "missing_fields": ["goal"],
        "user_info_retry_count": settings.USER_INFO_MAX_RETRIES + 5,
    }

    assert route_after_profile_check(state) == "exhausted"


async def test_a_state_with_no_counter_asks_rather_than_gives_up() -> None:
    """A run checkpointed before the counter existed must not start out exhausted."""
    state = _state(None) | {"missing_fields": ["goal"]}
    del state["user_info_retry_count"]

    assert route_after_profile_check(state) == "ask"


@pytest.mark.parametrize(
    ("missing_fields", "expected"), [([], "complete"), (["goal"], "ask")]
)
def test_route_after_profile_check_follows_the_completeness_flag(
    missing_fields: list[str], expected: str
) -> None:
    """Completeness is checked before the retry limit — a complete profile always plans."""
    state = initial_state("build me a plan", USER_ID) | {
        "missing_fields": missing_fields
    }
    assert route_after_profile_check(state) == expected
