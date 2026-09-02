"""Tests for the profile form: the fields it derives, and the submissions it accepts."""

import json

from src.schemas import UserProfile
from src.services.profile_form import (
    CHOICE,
    FORM_FIELDS,
    INTEGER,
    NUMBER,
    profile_form_fields,
    submitted_values,
    validate_profile_submission,
)

COMPLETE = {
    "age": 27,
    "sex": "MALE",
    "height_cm": 178.0,
    "current_weight_kg": 80.0,
    "activity_level": "MODERATE",
    "goal": "FAT_LOSS",
    "training_days_per_week": 4,
}


def _named(fields: list[dict]) -> dict[str, dict]:
    return {field["name"]: field for field in fields}


# --- The fields the form asks for ----------------------------------------------------------


def test_every_required_field_can_be_asked_for() -> None:
    """The form has to be able to collect everything the coach cannot plan without, or
    a run would reach the coach still missing a field and bounce straight back."""
    required = {
        name for name, field in UserProfile.model_fields.items() if field.is_required()
    }
    assert required <= set(FORM_FIELDS)


def test_a_field_the_form_has_no_input_for_is_never_asked_for() -> None:
    """``injuries`` and ``available_equipment`` are nested models — a number-or-choice
    form cannot collect them, so it must not claim to."""
    assert "injuries" not in FORM_FIELDS
    assert "available_equipment" not in FORM_FIELDS
    assert "preferences" not in FORM_FIELDS


def test_an_empty_profile_is_asked_for_every_required_field() -> None:
    """The first-plan case: nothing on file, so the form is the whole profile."""
    fields = profile_form_fields(None)

    assert [field["name"] for field in fields] == [
        "age",
        "sex",
        "height_cm",
        "current_weight_kg",
        "activity_level",
        "goal",
        "training_days_per_week",
    ]


def test_only_the_missing_fields_are_asked_for() -> None:
    """A profile that is only partly filled is not re-asked for what it already has."""
    stored = {"age": 27, "sex": "MALE"}

    names = [field["name"] for field in profile_form_fields(stored)]

    assert "age" not in names
    assert "sex" not in names
    assert "height_cm" in names


def test_a_drafted_optional_field_is_shown_for_confirmation() -> None:
    """``target_weight_kg`` is optional, so nothing makes the form ask for it — but a
    user who stated it should see it on the form rather than have it saved unseen."""
    fields = _named(profile_form_fields(COMPLETE, {"target_weight_kg": 75.0}))

    assert fields["target_weight_kg"]["required"] is False
    assert list(fields) == ["target_weight_kg"]


def test_a_field_input_carries_its_kind_options_and_bounds() -> None:
    """What the form renders is read off the model, so a constraint changed there cannot
    leave the form offering a value the model would reject."""
    fields = _named(profile_form_fields(None))

    assert fields["age"]["kind"] == INTEGER
    assert (fields["age"]["minimum"], fields["age"]["maximum"]) == (13.0, 100.0)
    assert fields["height_cm"]["kind"] == NUMBER
    assert fields["sex"]["kind"] == CHOICE
    assert fields["sex"]["options"] == ["MALE", "FEMALE"]
    assert fields["training_days_per_week"]["maximum"] == 7.0


def test_a_field_is_labelled_with_its_unit() -> None:
    """``height_cm`` asked for as "Height" would be filled in in feet sooner or later."""
    fields = _named(profile_form_fields(None))

    assert fields["height_cm"]["label"] == "Height (cm)"
    assert fields["training_days_per_week"]["label"] == "Training days per week"


# --- Reading a submission ------------------------------------------------------------------


def test_a_submission_keeps_only_profile_fields() -> None:
    """The submission is saved, so anything that is not a profile field is not stored."""
    assert submitted_values({"age": 27, "is_admin": True}) == {"age": 27}


def test_a_blank_answer_is_not_a_value() -> None:
    """An untouched form field is an unanswered one, not an instruction to store a blank."""
    assert submitted_values({"age": 27, "sex": "", "goal": None}) == {"age": 27}


def test_a_submission_may_arrive_as_json_text() -> None:
    """The Streamlit form posts fields, but an API client only has the message body."""
    assert submitted_values(json.dumps({"age": 27})) == {"age": 27}


def test_plain_text_is_not_a_submission() -> None:
    """A user typing a sentence at a form has answered nothing, and must be re-asked
    rather than have the sentence guessed at."""
    assert submitted_values("I'm 27") == {}


# --- Validating a submission ---------------------------------------------------------------


def test_a_complete_submission_validates_into_a_storable_profile() -> None:
    """The whole point of the gate: what comes out is a profile the coach can plan from."""
    validated, errors = validate_profile_submission(None, COMPLETE)

    assert errors == {}
    assert validated["age"] == 27
    assert validated["sex"] == "MALE"


def test_a_missing_required_field_is_reported_against_that_field() -> None:
    """The form re-asks by field, so the error has to name the field it belongs to."""
    validated, errors = validate_profile_submission(None, {"age": 27})

    assert validated == {}
    assert "sex" in errors
    assert "age" not in errors


def test_a_value_outside_its_bounds_is_rejected_with_its_reason() -> None:
    """Required-and-present is not enough: an 8-day training week has to be caught here
    rather than reaching the coach and failing verification later."""
    _, errors = validate_profile_submission(
        None, {**COMPLETE, "training_days_per_week": 8}
    )

    assert "training_days_per_week" in errors


def test_a_submission_completes_what_is_already_on_file() -> None:
    """The form only asks for what is missing, so validation has to judge the merge of
    the submission and the stored profile, not the submission alone."""
    stored = {"age": 27, "sex": "MALE", "height_cm": 178.0}
    submitted = {
        "current_weight_kg": 80.0,
        "activity_level": "MODERATE",
        "goal": "FAT_LOSS",
        "training_days_per_week": 4,
    }

    validated, errors = validate_profile_submission(stored, submitted)

    assert errors == {}
    assert validated["age"] == 27
    assert validated["current_weight_kg"] == 80.0


def test_a_stored_field_the_user_restated_is_overwritten() -> None:
    """A form the user corrects is a correction — the submitted value wins over the
    stored one without a separate confirmation step."""
    validated, errors = validate_profile_submission(
        {**COMPLETE, "current_weight_kg": 95.0}, {"current_weight_kg": 80.0}
    )

    assert errors == {}
    assert validated["current_weight_kg"] == 80.0
