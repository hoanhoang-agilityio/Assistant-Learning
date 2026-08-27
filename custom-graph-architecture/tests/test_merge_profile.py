"""Tests for the ``merge_profile`` node and the merge rules behind it."""

import pytest

from src.core.langgraph.nodes.merge_profile import merge_profile
from src.schemas import initial_state
from src.services.profile import (
    merge_injuries,
    merge_profile_updates,
    pending_revision_fields,
    usable_profile_fields,
)
from src.services.turn import InjuryStatement, ProfileStatement
from tests.test_load_user_context import COMPLETE_PROFILE, USER_ID


def _state(statement: ProfileStatement, **overrides: object) -> dict:
    """A state as it stands once ``parse_turn`` has read the message."""
    return initial_state("build me a plan", USER_ID) | {
        "extracted_facts": statement.model_dump(mode="json"),
        **overrides,
    }


# --- Filtering what the parser returned --------------------------------------------------


def test_unstated_fields_are_dropped() -> None:
    """A null means the user did not say it — storing it would erase what they had."""
    assert usable_profile_fields(ProfileStatement(age=34)) == {"age": 34}


@pytest.mark.parametrize("age", [12, 101])
def test_an_out_of_range_age_is_refused(age: int) -> None:
    """The spec bounds age at 13-100; long-term memory must not take anything else."""
    assert usable_profile_fields(ProfileStatement(age=age, sex="MALE")) == {
        "sex": "MALE"
    }


@pytest.mark.parametrize("days", [0, 8])
def test_an_impossible_training_week_is_refused(days: int) -> None:
    """A plan cannot be built for 0 or 8 training days."""
    assert usable_profile_fields(ProfileStatement(training_days_per_week=days)) == {}


@pytest.mark.parametrize(
    "field", ["height_cm", "current_weight_kg", "target_weight_kg"]
)
def test_a_non_positive_measurement_is_refused(field: str) -> None:
    """Every body measurement in the spec is greater than zero."""
    assert usable_profile_fields(ProfileStatement(**{field: 0.0})) == {}


def test_one_bad_field_does_not_discard_the_good_ones() -> None:
    """Dropping the whole message would ask the user to repeat what they got right."""
    statement = ProfileStatement(age=200, sex="FEMALE", goal="FAT_LOSS")

    assert usable_profile_fields(statement) == {"sex": "FEMALE", "goal": "FAT_LOSS"}


def test_fields_to_revise_is_never_read_as_a_profile_value() -> None:
    """The revision list rides on the same structured output; it must not leak into the profile."""
    statement = ProfileStatement(age=34, fields_to_revise=["target_weight_kg"])

    assert usable_profile_fields(statement) == {"age": 34}


def test_injuries_are_not_read_as_a_scalar_profile_value() -> None:
    """Injuries merge by body part; the scalar path must leave them alone."""
    statement = ProfileStatement(injuries=[InjuryStatement(body_part="knee")])

    assert usable_profile_fields(statement) == {}


# --- Injuries ----------------------------------------------------------------------------


def test_a_first_injury_is_recorded() -> None:
    """Nothing else in the graph writes injuries, so the safety check depends on this."""
    merged = merge_injuries(None, [InjuryStatement(body_part="left knee")])

    assert merged == [{"body_part": "left knee", "status": "ACTIVE"}]


def test_the_same_body_part_is_updated_rather_than_duplicated() -> None:
    """Mentioning a knee twice is one injury, not two, or the plan is filtered twice over."""
    stored = [{"body_part": "knee", "status": "ACTIVE", "severity": "mild"}]

    merged = merge_injuries(
        stored, [InjuryStatement(body_part="Knee ", status="RESOLVED")]
    )

    assert merged == [{"body_part": "Knee ", "status": "RESOLVED", "severity": "mild"}]


def test_updating_an_injury_keeps_the_restrictions_already_on_it() -> None:
    """Restrictions come from elsewhere; a passing mention must not wipe them."""
    stored = [
        {
            "body_part": "shoulder",
            "status": "ACTIVE",
            "restrictions": [{"movement_pattern": "PUSH", "action": "PROHIBITED"}],
        }
    ]

    merged = merge_injuries(stored, [InjuryStatement(body_part="shoulder")])

    assert merged[0]["restrictions"] == [
        {"movement_pattern": "PUSH", "action": "PROHIBITED"}
    ]


def test_a_different_body_part_is_appended() -> None:
    """Two injuries constrain the plan in two ways; one must not overwrite the other."""
    stored = [{"body_part": "knee", "status": "ACTIVE"}]

    merged = merge_injuries(stored, [InjuryStatement(body_part="shoulder")])

    assert [injury["body_part"] for injury in merged] == ["knee", "shoulder"]


def test_a_message_with_no_injuries_leaves_the_stored_ones_alone() -> None:
    """Silence about an injury is not a report that it healed."""
    profile = {"injuries": [{"body_part": "knee", "status": "ACTIVE"}]}

    merged = merge_profile_updates(profile, ProfileStatement(age=34))

    assert merged["injuries"] == [{"body_part": "knee", "status": "ACTIVE"}]


# --- Merging stated values and revision flags into a runtime profile ---------------------


def test_a_stated_value_overwrites_the_stored_one() -> None:
    """A correction must win over whatever was already on file."""
    merged = merge_profile_updates(
        {"current_weight_kg": 82.5}, ProfileStatement(current_weight_kg=80.0)
    )

    assert merged["current_weight_kg"] == 80.0


def test_a_field_flagged_without_a_value_is_cleared() -> None:
    """ "my target is wrong" with no new number must blank it, not leave the old value."""
    merged = merge_profile_updates(
        {"target_weight_kg": 70.0},
        ProfileStatement(fields_to_revise=["target_weight_kg"]),
    )

    assert merged["target_weight_kg"] is None


def test_a_field_flagged_and_restated_in_the_same_message_keeps_the_new_value() -> None:
    """ "my target is wrong, it's 65kg" must not clear the value it just gave."""
    merged = merge_profile_updates(
        {"target_weight_kg": 70.0},
        ProfileStatement(target_weight_kg=65.0, fields_to_revise=["target_weight_kg"]),
    )

    assert merged["target_weight_kg"] == 65.0


def test_merging_onto_no_stored_profile_starts_from_empty() -> None:
    """A first-ever message that states values must not need a profile to merge onto."""
    assert merge_profile_updates(None, ProfileStatement(age=34)) == {"age": 34}


def test_pending_revision_fields_drops_ones_already_filled_in() -> None:
    """A revision satisfied by this merge must stop being asked for."""
    profile = {"target_weight_kg": 65.0, "goal": None}

    assert pending_revision_fields(profile, ["target_weight_kg", "goal"]) == ["goal"]


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_pending_revision_fields_treats_blank_variants_as_still_pending(
    blank: object,
) -> None:
    """An empty string left behind by a merge is still an unanswered field."""
    assert pending_revision_fields({"goal": blank}, ["goal"]) == ["goal"]


# --- The node ----------------------------------------------------------------------------


async def test_the_node_merges_stated_values_onto_the_loaded_profile() -> None:
    """The node writes to runtime state only — ``persist_profile`` owns the store."""
    statement = ProfileStatement(age=34, sex="MALE", goal="FAT_LOSS")

    actual_update = await merge_profile(_state(statement))

    assert actual_update == {
        "profile": {"age": 34, "sex": "MALE", "goal": "FAT_LOSS"},
        "revision_fields": [],
    }


async def test_the_node_merges_onto_what_is_already_in_state() -> None:
    """Fields loaded from the store, or collected earlier in this run, must survive."""
    actual_update = await merge_profile(
        _state(ProfileStatement(goal="FAT_LOSS"), profile={"age": 34})
    )

    assert actual_update["profile"] == {"age": 34, "goal": "FAT_LOSS"}


async def test_a_message_stating_nothing_leaves_the_profile_alone() -> None:
    """A refusal or a failed parse must not blank out what the user already gave."""
    actual_update = await merge_profile(
        _state(ProfileStatement(), profile=COMPLETE_PROFILE)
    )

    assert actual_update["profile"] == COMPLETE_PROFILE


async def test_a_revision_request_without_a_value_is_tracked_in_state() -> None:
    """ "update my target" with no number must clear it and remember to keep asking."""
    actual_update = await merge_profile(
        _state(
            ProfileStatement(fields_to_revise=["target_weight_kg"]),
            profile=COMPLETE_PROFILE | {"target_weight_kg": 70.0},
        )
    )

    assert actual_update["profile"]["target_weight_kg"] is None
    assert actual_update["revision_fields"] == ["target_weight_kg"]


async def test_a_revision_answered_in_the_same_turn_is_not_left_pending() -> None:
    """ "my target is wrong, it's 65kg" resolves in one turn — nothing left to ask."""
    actual_update = await merge_profile(
        _state(
            ProfileStatement(
                target_weight_kg=65.0, fields_to_revise=["target_weight_kg"]
            ),
            profile=COMPLETE_PROFILE | {"target_weight_kg": 70.0},
        )
    )

    assert actual_update["profile"]["target_weight_kg"] == 65.0
    assert actual_update["revision_fields"] == []


async def test_a_revision_field_carried_from_an_earlier_round_stays_pending() -> None:
    """A message about something else must not silently drop an outstanding revision."""
    actual_update = await merge_profile(
        _state(
            ProfileStatement(),
            profile=COMPLETE_PROFILE | {"target_weight_kg": None},
            revision_fields=["target_weight_kg"],
        )
    )

    assert actual_update["revision_fields"] == ["target_weight_kg"]


async def test_a_turn_that_was_never_parsed_leaves_the_profile_alone() -> None:
    """Reached without ``extracted_facts``, the node must not crash the run."""
    state = initial_state("build me a plan", USER_ID) | {"profile": COMPLETE_PROFILE}

    assert (await merge_profile(state))["profile"] == COMPLETE_PROFILE
