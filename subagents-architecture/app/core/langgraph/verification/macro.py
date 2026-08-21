"""Macro check: compare computed macros against the nutrition rubric.

Pure arithmetic against thresholds. No LLM — a model participating in a
numeric comparison is pure added risk.
"""

from app.schemas.graph import Issue

_LOCATION = "Nutrition targets"


def check_macro(computed_macros: dict, profile: dict, rubric: dict) -> list[Issue]:
    """Assess a macro target set against the rubric.

    Args:
        computed_macros: Targets to assess. Expected keys ``kcal``,
            ``protein_g``, ``fat_g`` and optionally ``tdee``.
        profile: User profile. Reads ``weight_kg`` and ``sex``.
        rubric: The ``macro_rules`` rubric.

    Returns:
        One issue per violated rule, empty when everything passes.
    """
    weight_kg = profile.get("weight_kg")
    if not weight_kg:
        return [
            _issue(
                "info",
                "Body weight is missing, so protein and fat targets were not assessed.",
                "macro.inputs.weight_kg",
            )
        ]

    issues: list[Issue] = []
    issues.extend(_check_protein(computed_macros, weight_kg, rubric))
    issues.extend(_check_fat(computed_macros, weight_kg, rubric))
    issues.extend(_check_floor(computed_macros, profile, rubric))
    issues.extend(_check_deficit(computed_macros, rubric))
    return issues


def _check_protein(macros: dict, weight_kg: float, rubric: dict) -> list[Issue]:
    """Flag protein below the floor or implausibly high."""
    protein_g = macros.get("protein_g")
    if protein_g is None:
        return [_issue("info", "No protein target to assess.", "macro.protein_g_per_kg")]

    rule = rubric["protein_g_per_kg"]
    per_kg = protein_g / weight_kg

    if per_kg < rule["min"]:
        return [
            _issue(
                "block",
                f"Protein is {per_kg:.1f} g/kg, below the {rule['min']} g/kg floor. "
                f"Target {rule['target']} g/kg — about {round(rule['target'] * weight_kg)} g/day.",
                "macro.protein_g_per_kg.min",
                suggestion={"protein_g": round(rule["target"] * weight_kg)},
            )
        ]
    if per_kg > rule["max"]:
        return [
            _issue(
                "warn",
                f"Protein is {per_kg:.1f} g/kg, above the {rule['max']} g/kg the rubric "
                "treats as useful. Not harmful, but those calories buy more elsewhere.",
                "macro.protein_g_per_kg.max",
                suggestion={"protein_g": round(rule["target"] * weight_kg)},
            )
        ]
    return []


def _check_fat(macros: dict, weight_kg: float, rubric: dict) -> list[Issue]:
    """Flag fat below the hormonal-function floor."""
    fat_g = macros.get("fat_g")
    if fat_g is None:
        return [_issue("info", "No fat target to assess.", "macro.fat_g_per_kg")]

    minimum = rubric["fat_g_per_kg"]["min"]
    per_kg = fat_g / weight_kg
    if per_kg < minimum:
        return [
            _issue(
                "block",
                f"Fat is {per_kg:.1f} g/kg, below the {minimum} g/kg floor.",
                "macro.fat_g_per_kg.min",
                suggestion={"fat_g": round(minimum * weight_kg)},
            )
        ]
    return []


def _check_floor(macros: dict, profile: dict, rubric: dict) -> list[Issue]:
    """Flag a calorie target below the absolute floor for the user's sex."""
    kcal = macros.get("kcal")
    sex = profile.get("sex")
    if kcal is None:
        return [_issue("info", "No calorie target to assess.", "macro.floor_kcal")]
    if sex not in rubric["floor_kcal"]:
        return [
            _issue(
                "info",
                "Sex is not recorded, so the calorie floor was not assessed.",
                "macro.floor_kcal",
            )
        ]

    floor = rubric["floor_kcal"][sex]
    if kcal < floor:
        return [
            _issue(
                "block",
                f"{round(kcal)} kcal/day is below the {floor} kcal floor.",
                "macro.floor_kcal",
                suggestion={"kcal": floor},
            )
        ]
    return []


def _check_deficit(macros: dict, rubric: dict) -> list[Issue]:
    """Flag a deficit that is too aggressive relative to maintenance."""
    kcal = macros.get("kcal")
    tdee = macros.get("tdee")
    if kcal is None or not tdee:
        return []

    deficit_pct = (tdee - kcal) / tdee * 100
    maximum = rubric["deficit"]["max_pct_tdee"]
    if deficit_pct > maximum:
        return [
            _issue(
                "block",
                f"The deficit is {deficit_pct:.0f}% of maintenance, above the {maximum}% cap.",
                "macro.deficit.max_pct_tdee",
                suggestion={"kcal": round(tdee * (1 - maximum / 100))},
            )
        ]
    return []


def _issue(severity: str, message: str, rubric_ref: str, suggestion: dict | None = None) -> Issue:
    """Build a macro issue.

    Args:
        severity: ``"info"``, ``"warn"`` or ``"block"``.
        message: User-facing explanation.
        rubric_ref: Dotted path of the rule that fired.
        suggestion: Replacement values, when there is a concrete fix.

    Returns:
        The issue.
    """
    return Issue(
        source="macro",
        severity=severity,
        location=_LOCATION,
        message=message,
        suggestion=suggestion,
        rubric_ref=rubric_ref,
    )
