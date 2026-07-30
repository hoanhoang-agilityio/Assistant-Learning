"""User-facing labels for profile fields and enum values."""

PROFILE_FIELD_LABELS: dict[str, str] = {
    "age": "age",
    "sex": "sex",
    "height_cm": "height (cm)",
    "current_weight_kg": "current weight (kg)",
    "target_weight_kg": "target weight (kg)",
    "weight_delta_kg": "weight change target (kg)",
    "horizon_weeks": "goal timeline (weeks)",
    "weekly_rate_kg": "weekly rate target (kg)",
    "activity_level": "training frequency",
    "goal": "fitness goal",
}

GOAL_LABELS: dict[str, str] = {
    "fat_loss": "Fat loss",
    "muscle_gain": "Muscle gain",
    "recomposition": "Body recomposition",
    "maintenance": "Maintenance",
    "strength": "Strength",
    "endurance": "Endurance",
    "general_fitness": "General fitness",
}

ACTIVITY_LABELS: dict[str, str] = {
    "sedentary": "Sedentary",
    "gym_1x_week": "Gym 1× per week",
    "gym_2x_week": "Gym 2× per week",
    "gym_3x_week": "Gym 3× per week",
    "gym_4x_week": "Gym 4× per week",
    "gym_5x_week": "Gym 5× per week",
    "gym_6x_week": "Gym 6× per week",
}


def label_for_profile_field(field_name: str) -> str:
    """Return a friendly label for a profile field key."""
    return PROFILE_FIELD_LABELS.get(field_name, field_name.replace("_", " "))


def format_missing_profile_prompt(missing_fields: list[str]) -> str:
    """Build a user-friendly prompt listing missing profile details."""
    labels = [label_for_profile_field(field) for field in missing_fields if field]
    if not labels:
        return "Please share a few more details about yourself so we can build your plan."
    if len(labels) == 1:
        return f"Please provide your {labels[0]}."
    if len(labels) == 2:
        return f"Please provide your {labels[0]} and {labels[1]}."
    joined = ", ".join(labels[:-1])
    return f"Please provide your {joined}, and {labels[-1]}."


def format_goal_label(goal: str) -> str:
    """Return a friendly label for a goal enum value."""
    return GOAL_LABELS.get(goal, goal.replace("_", " ").title())


def format_activity_label(activity_level: str) -> str:
    """Return a friendly label for an activity level enum value."""
    return ACTIVITY_LABELS.get(activity_level, activity_level.replace("_", " "))
