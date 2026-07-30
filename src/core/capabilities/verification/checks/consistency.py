"""Consistency check: do the draft's numbers match the computed macro/training plan?"""

import re
from typing import Any


def consistency_check_data(
    draft_plan: str,
    macro_targets: dict[str, Any],
    training_plan: dict[str, Any],
    plan_blueprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    if not macro_targets:
        issues.append("missing_macro_targets")
    if not training_plan:
        issues.append("missing_training_plan_summary")
    if plan_blueprint is not None and not plan_blueprint:
        issues.append("missing_plan_blueprint")

    calories = macro_targets.get("calories")
    protein_g = macro_targets.get("protein_g")
    if calories is not None and str(calories) not in draft_plan:
        issues.append("draft_missing_calorie_target")
    if protein_g is not None and str(protein_g) not in draft_plan:
        issues.append("draft_missing_protein_target")

    expected_sessions = training_plan.get("sessions")
    if isinstance(expected_sessions, int):
        day_matches = re.findall(r"### Day \d+", draft_plan)
        if len(day_matches) != expected_sessions:
            issues.append("training_day_count_mismatch")

    return {
        "passed": not issues,
        "issues": issues,
    }
