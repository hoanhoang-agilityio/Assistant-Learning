"""How a change to the profile reads to the user: the summary they approve, and the line that confirms it."""

from typing import Any

from src.schemas import UserProfile

PROFILE_UPDATED = "✅ Profile updated."

UPDATE_LEAD = "Got it! I'll save these details to your profile:"
UPDATE_ASK = "Save these details?"

NOTHING_SET = "none"

# Fields whose stored name says more than the user needs to read.
LABELS = {"training_days_per_week": "Training"}

# The unit a field's name carries, shown against the value rather than the label.
UNITS = ("cm", "kg")

SUFFIXES = {"training_days_per_week": "days/week"}


def _label(name: str) -> str:
    """A field's name as the summary shows it."""

    if name in LABELS:
        return LABELS[name]
    words = name.split("_")
    if words[-1] in UNITS:
        words = words[:-1]
    return " ".join(words).capitalize()


def _number(value: float) -> str:
    """A measurement without the trailing zero a whole number would otherwise carry."""

    return str(int(value)) if float(value).is_integer() else str(value)


def _scalar(value: Any) -> str:
    """One stored value in the user's own words rather than the store's."""

    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int | float):
        return _number(value)
    if isinstance(value, str):
        return value.replace("_", " ").capitalize()
    return str(value)


def _value(name: str, value: Any) -> str:
    """One field's value, carrying whatever unit its name implies."""

    if isinstance(value, dict):
        listed = [
            _scalar(item)
            for nested in value.values()
            if isinstance(nested, list)
            for item in nested
        ]
        return ", ".join(listed) or NOTHING_SET
    if isinstance(value, list):
        return ", ".join(_scalar(item) for item in value) or NOTHING_SET
    if value is None:
        return NOTHING_SET

    rendered = _scalar(value)
    unit = name.rsplit("_", maxsplit=1)[-1]
    if unit in UNITS:
        return f"{rendered} {unit}"
    if name in SUFFIXES:
        return f"{rendered} {SUFFIXES[name]}"
    return rendered


def update_lines(updates: dict[str, Any]) -> list[str]:
    """One line per field a change would write, in the order the profile declares them."""

    return [
        f"- {_label(name)}: {_value(name, updates[name])}"
        for name in UserProfile.model_fields
        if name in updates
    ]


def update_summary(updates: dict[str, Any]) -> str:
    """The whole change as one thing to approve, rather than one tool call per field."""

    return "\n".join([UPDATE_LEAD, "", *update_lines(updates), "", UPDATE_ASK])


__all__ = [
    "PROFILE_UPDATED",
    "UPDATE_ASK",
    "UPDATE_LEAD",
    "update_lines",
    "update_summary",
]
