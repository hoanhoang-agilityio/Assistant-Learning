from core.profile.labels import (
    format_activity_label,
    format_goal_label,
    format_missing_profile_prompt,
    label_for_profile_field,
)


def test_label_for_profile_field() -> None:
    assert label_for_profile_field("age") == "age"
    assert label_for_profile_field("height_cm") == "height (cm)"
    assert label_for_profile_field("current_weight_kg") == "current weight (kg)"
    assert label_for_profile_field("activity_level") == "training frequency"


def test_format_missing_profile_prompt_single_field() -> None:
    assert format_missing_profile_prompt(["sex"]) == "Please provide your sex."


def test_format_missing_profile_prompt_two_fields() -> None:
    message = format_missing_profile_prompt(["age", "sex"])
    assert message == "Please provide your age and sex."


def test_format_missing_profile_prompt_many_fields() -> None:
    message = format_missing_profile_prompt(
        ["activity_level", "age", "current_weight_kg", "height_cm", "sex", "target_weight_kg"]
    )
    assert message == (
        "Please provide your training frequency, age, current weight (kg), "
        "height (cm), sex, and target weight (kg)."
    )


def test_format_missing_profile_prompt_empty() -> None:
    assert "details" in format_missing_profile_prompt([])


def test_format_goal_label() -> None:
    assert format_goal_label("muscle_gain") == "Muscle gain"
    assert format_goal_label("fat_loss") == "Fat loss"


def test_format_activity_label() -> None:
    assert format_activity_label("gym_5x_week") == "Gym 5× per week"
