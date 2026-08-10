"""Macro arithmetic.

Pure functions, no LLM. This is
plain arithmetic, so a model participating in it is risk with no upside.

These functions compute what the plan *targets*. Whether those targets are
acceptable is a separate question answered by
``app/core/langgraph/checks/macro.py`` against the rubric.
Keeping the two apart is what lets the verifier disagree with the calculator —
the calculator applies a requested deficit, the verifier refuses one that is too
deep, and neither has to know the other's thresholds.
"""

from typing import Literal

Sex = Literal["male", "female"]

# Mifflin-St Jeor, the published equation. The sex constant is the only term
# that differs between the two forms.
_SEX_CONSTANT: dict[str, int] = {"male": 5, "female": -161}

# Standard activity multipliers applied to BMR to reach TDEE. `sedentary` here
# means the user's baseline life, not their training — the training itself is
# already counted, which is why adding a session raises TDEE and breaks a
# previously-set deficit.
ACTIVITY_FACTORS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

# Extra expenditure per training session per week, as a fraction of BMR. This is
# the term that makes 4 days and 5 days produce different macros.
_PER_SESSION_FACTOR = 0.025

_GOAL_ADJUSTMENT: dict[str, float] = {
    "fat_loss": -0.20,
    "recomp": -0.10,
    "general_health": 0.0,
    "muscle_gain": 0.10,
}

_KCAL_PER_G = {"protein": 4, "carbs": 4, "fat": 9}


def mifflin_st_jeor(weight_kg: float, height_cm: float, age: int, sex: Sex) -> float:
    """Compute basal metabolic rate.

    Args:
        weight_kg: Body weight in kilograms.
        height_cm: Height in centimetres.
        age: Age in years.
        sex: ``"male"`` or ``"female"``.

    Returns:
        BMR in kcal/day.

    Raises:
        ValueError: When ``sex`` is not one the equation defines a constant for.
    """
    if sex not in _SEX_CONSTANT:
        raise ValueError(f"unsupported sex for the Mifflin-St Jeor equation: {sex!r}")
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + _SEX_CONSTANT[sex]


def compute_tdee(bmr: float, activity_level: str, sessions_per_week: int) -> float:
    """Compute total daily energy expenditure.

    Args:
        bmr: Basal metabolic rate.
        activity_level: A key of ``ACTIVITY_FACTORS``.
        sessions_per_week: Training sessions the plan prescribes.

    Returns:
        TDEE in kcal/day.

    Raises:
        ValueError: When ``activity_level`` is not a known key. Defaulting
            silently would produce a number that looks authoritative and is
            wrong by up to 700 kcal.
    """
    if activity_level not in ACTIVITY_FACTORS:
        raise ValueError(
            f"unknown activity_level {activity_level!r}; expected one of {sorted(ACTIVITY_FACTORS)}"
        )
    factor = ACTIVITY_FACTORS[activity_level] + sessions_per_week * _PER_SESSION_FACTOR
    return bmr * factor


def split_macros(
    kcal: float, weight_kg: float, protein_g_per_kg: float = 2.0, fat_g_per_kg: float = 0.8
) -> dict[str, int]:
    """Split a calorie target into protein, fat and carbohydrate.

    Protein and fat are set from body weight first, because both have floors the
    rubric enforces. Carbohydrate takes whatever calories remain — it is the term
    with no minimum, so it is the one that absorbs the deficit.

    Args:
        kcal: Daily calorie target.
        weight_kg: Body weight in kilograms.
        protein_g_per_kg: Protein target per kilogram.
        fat_g_per_kg: Fat target per kilogram.

    Returns:
        ``{"protein_g": ..., "fat_g": ..., "carbs_g": ...}``, rounded to whole
        grams. ``carbs_g`` is never negative: an impossible target leaves it at
        zero and the verifier's calorie-floor rule is what reports the problem.
    """
    protein_g = round(protein_g_per_kg * weight_kg)
    fat_g = round(fat_g_per_kg * weight_kg)
    remaining = kcal - protein_g * _KCAL_PER_G["protein"] - fat_g * _KCAL_PER_G["fat"]
    carbs_g = max(0, round(remaining / _KCAL_PER_G["carbs"]))
    return {"protein_g": protein_g, "fat_g": fat_g, "carbs_g": carbs_g}


def calc_macros(profile: dict, sessions_per_week: int, goal: str) -> dict:
    """Compute the full macro target set for a profile and a plan.

    Called from ``app.core.langgraph.scoring.score``, which is the one place
    macros and rubric checks are computed together. Deliberately a plain function
    rather than a tool: it must run on every build, change and review, so there
    is nothing for a model to decide.

    Args:
        profile: Reads ``weight_kg``, ``height_cm``, ``age``, ``sex`` and
            ``activity_level``.
        sessions_per_week: Sessions the plan prescribes.
        goal: A key of ``_GOAL_ADJUSTMENT``.

    Returns:
        ``{"bmr", "tdee", "kcal", "protein_g", "fat_g", "carbs_g", "goal"}``.
        ``bmr``, ``tdee`` and ``kcal`` are rounded to whole calories.

    Raises:
        KeyError: When a required profile field is absent. The profile gate
            on the calling tool runs before this and is what asks the user, so
            reaching here without a field is a routing bug, not user error.
        ValueError: When sex, activity level or goal is not recognised.
    """
    if goal not in _GOAL_ADJUSTMENT:
        raise ValueError(f"unknown goal {goal!r}; expected one of {sorted(_GOAL_ADJUSTMENT)}")

    bmr = mifflin_st_jeor(
        weight_kg=profile["weight_kg"],
        height_cm=profile["height_cm"],
        age=profile["age"],
        sex=profile["sex"],
    )
    tdee = compute_tdee(bmr, profile["activity_level"], sessions_per_week)
    kcal = tdee * (1 + _GOAL_ADJUSTMENT[goal])

    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "kcal": round(kcal),
        "goal": goal,
        **split_macros(kcal, profile["weight_kg"]),
    }


__all__ = [
    "ACTIVITY_FACTORS",
    "calc_macros",
    "compute_tdee",
    "mifflin_st_jeor",
    "split_macros",
]
