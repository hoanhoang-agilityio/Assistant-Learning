"""Safety check: which fitness safety flags and unsafe phrasings block delivery."""

from typing import Any

CRITICAL_SAFETY_FLAGS = {
    "calories_below_safe_minimum",
    "aggressive_calorie_deficit",
    "training_frequency_too_high",
    "weekly_training_volume_too_high",
}
_SAFETY_SCAN_EXCLUDED_HEADERS = (
    "## Evidence Summary",
    "## Evidence Applied",
    "## Verification Feedback Applied",
    "## Safety Warnings",
    "## Notes",
    "## Program Blueprint",
)


def _draft_text_for_safety_scan(draft_plan: str) -> str:
    """Scan only prescription sections; ignore evidence/feedback metadata in the draft."""
    if not draft_plan.strip():
        return ""
    lines = draft_plan.splitlines()
    scanned_lines: list[str] = []
    include_section = False
    for line in lines:
        if line.startswith("## "):
            include_section = line not in _SAFETY_SCAN_EXCLUDED_HEADERS
        if include_section:
            scanned_lines.append(line)
    if scanned_lines:
        return "\n".join(scanned_lines)
    return draft_plan


def safety_check_data(
    draft_plan: str,
    safety_flags: list[str],
    *,
    fitness_safety_passed: bool | None = None,
) -> dict[str, Any]:
    """fitness_safety_passed is the actual pass/fail boolean Fitness's own
    validate_workout_safety_data computed (see fitness/utils.py's
    write_fitness_artifacts, which persists it to fitness/safety_passed.json).

    Previously this check only ever re-derived pass/fail from whether any of
    `safety_flags` appeared in the small CRITICAL_SAFETY_FLAGS allowlist below
    -- every other flag Fitness can emit (equipment mismatch, duplicate
    exercise, invalid set count, wrong day count, ...) was silently ignored.
    When fitness_safety_passed is available it's authoritative: any fitness-
    side safety failure blocks delivery, not just the allowlisted subset.
    None (an older workspace predating this field, or a call site that hasn't
    threaded it through) falls back to the flags-only check exactly as before.
    """
    issues = [flag for flag in safety_flags if flag in CRITICAL_SAFETY_FLAGS]
    unsafe_terms = ("unsafe", "extreme deficit", "excessive volume")
    draft_lower = _draft_text_for_safety_scan(draft_plan).lower()
    for term in unsafe_terms:
        if term in draft_lower:
            issues.append(f"unsafe_language:{term}")
    if fitness_safety_passed is False:
        issues.append("fitness_safety_check_failed")

    return {
        "passed": not issues,
        "issues": sorted(set(issues)),
    }
