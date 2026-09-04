"""What a profile change looks like to the user: the summary they approve, in their own terms.

The tool call behind it writes stored field names and enum values; none of that is what a
person should be asked to say yes to.
"""

from src.services.profile_presentation import (
    PROFILE_UPDATED,
    UPDATE_ASK,
    update_lines,
    update_summary,
)

STATED = {
    "age": 27,
    "sex": "MALE",
    "height_cm": 178.0,
    "current_weight_kg": 80.0,
    "target_weight_kg": 75.0,
    "training_days_per_week": 4,
}

# --- One change, one question ------------------------------------------------------------


def test_every_field_of_the_change_is_one_line_of_one_question() -> None:
    """Six fields the user stated in one sentence are one thing to approve, not six."""
    assert update_summary(STATED) == (
        "Got it! I'll save these details to your profile:\n"
        "\n"
        "- Age: 27\n"
        "- Sex: Male\n"
        "- Height: 178 cm\n"
        "- Current weight: 80 kg\n"
        "- Target weight: 75 kg\n"
        "- Training: 4 days/week\n"
        "\n"
        "Save these details?"
    )


def test_the_summary_ends_in_a_question() -> None:
    """It is an approval prompt, so it has to read as one."""
    assert update_summary({"age": 27}).endswith(UPDATE_ASK)


def test_the_fields_read_in_the_order_the_profile_declares_them() -> None:
    """Whatever order the model listed them in, the user reads one stable shape."""
    scrambled = dict(reversed(list(STATED.items())))

    assert update_lines(scrambled) == update_lines(STATED)


# --- The store's own shapes are not what the user reads ------------------------------------


def test_an_enum_value_reads_as_words() -> None:
    assert update_lines({"goal": "FAT_LOSS"}) == ["- Goal: Fat loss"]


def test_a_whole_measurement_keeps_no_trailing_zero() -> None:
    """``178.0 cm`` is a float, not a height anyone writes down."""
    assert update_lines({"height_cm": 178.0}) == ["- Height: 178 cm"]


def test_a_fractional_measurement_keeps_its_precision() -> None:
    assert update_lines({"current_weight_kg": 80.5}) == ["- Current weight: 80.5 kg"]


def test_a_list_reads_as_a_list() -> None:
    assert update_lines({"preferences": ["dumbbells", "mornings"]}) == [
        "- Preferences: Dumbbells, Mornings"
    ]


def test_an_empty_list_says_so_rather_than_showing_brackets() -> None:
    assert update_lines({"injuries": []}) == ["- Injuries: none"]


def test_nested_equipment_reads_as_one_list() -> None:
    """Two stored lists, one thing the user owns."""
    assert update_lines(
        {
            "available_equipment": {
                "equipment": ["DUMBBELL"],
                "other_equipment": ["bands"],
            }
        }
    ) == ["- Available equipment: Dumbbell, Bands"]


# --- The confirmation ---------------------------------------------------------------------


def test_the_confirmation_says_nothing_about_the_tools_that_ran() -> None:
    """The user never sees the machinery, only that the change went through."""
    assert PROFILE_UPDATED == "✅ Profile updated."
