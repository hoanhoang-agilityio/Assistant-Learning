import re
from typing import Any

from pydantic import ValidationError

from core.shared.profile.extraction import extract_profile_from_query
from core.shared.profile.goal_spec import GoalSpec, derive_goal_spec
from core.shared.profile.normalize import (
    _normalize_days_per_week,
    merge_profile_sources,
    resolve_target_weight,
)
from core.shared.profile.schema import (
    CONSTRAINT_FIELDS,
    GOAL_REQUIRED_FIELDS,
    REQUIRED_PROFILE_FIELDS,
    Constraints,
    ExtractedProfile,
    Profile,
)
from core.shared.profile.store import load_run_profile
from core.shared.profile.store import persist_profile as persist_profile

REVISION_OVERRIDE_FIELDS: tuple[str, ...] = (
    *CONSTRAINT_FIELDS,
    "goal",
    "target_weight_kg",
    "weight_delta_kg",
    "horizon_weeks",
)

_DAYS_PER_WEEK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(\d+)\s*[- ]?\s*days?\s*(?:per|/|a)?\s*week\b", re.IGNORECASE),
    re.compile(r"\btrain(?:ing)?\s+(\d+)\s+days?\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s*[- ]day\s+(?:training|workout|plan)\b", re.IGNORECASE),
)


def _parse_days_per_week_from_text(text: str) -> int | None:
    for pattern in _DAYS_PER_WEEK_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        days = int(match.group(1))
        return min(max(days, 0), 6)
    return None


def resolve_extraction_query(query: str, user_profile: dict[str, Any]) -> str:
    """Use only the latest user message when HITL resume appends clarifications to query."""
    if not user_profile:
        return query
    if "\n" in query:
        latest = query.rsplit("\n", 1)[-1].strip()
        if latest:
            return latest
    return query


def apply_revision_overrides(
    profile: dict[str, Any],
    revision_feedback: str,
) -> dict[str, Any]:
    """Re-extract plan-change fields from revision text and override the merged profile.

    Raw fields only survive into the returned profile: a delta phrase in the revision text
    (`weight_delta_kg`) is folded into `target_weight_kg` via `resolve_target_weight` and
    discarded, exactly like the query-extraction path in `merge_profile_sources`.
    """
    stripped = revision_feedback.strip()
    if not stripped:
        return profile
    from core.shared.profile.normalize import normalize_extracted_profile

    extracted = extract_profile_from_query(stripped)
    overrides = normalize_extracted_profile(extracted)
    updated = dict(profile)
    for field_name in REVISION_OVERRIDE_FIELDS:
        value = overrides.get(field_name)
        if value is not None and value != "":
            updated[field_name] = value
    resolve_target_weight(updated)
    parsed_days = _parse_days_per_week_from_text(stripped)
    if parsed_days is not None:
        updated["days_per_week"] = parsed_days
    _normalize_days_per_week(updated)
    # Internal signal, popped by `_extract_node`: whether *this* revision text explicitly
    # named a training-frequency target, vs. days_per_week merely being carried over from the
    # prior profile. The Fitness subgraph needs this to know when profile.days_per_week should
    # override edit-derived day counts (see resolve_expected_day_count).
    updated["_days_per_week_explicit"] = (
        parsed_days is not None or overrides.get("days_per_week") is not None
    )
    return updated


def validate_profile_completeness(profile: dict[str, Any], goal_spec: GoalSpec) -> dict[str, Any]:
    """Rule-based completeness + goal-feasibility checks.

    `goal_spec` must be derived (via `derive_goal_spec`) by the caller from this same
    `profile` -- passed in explicitly rather than recomputed here, per the single-derivation
    threading rule (see `_validate_node`, the sole caller).
    """
    missing_fields: list[str] = []
    for field_name in REQUIRED_PROFILE_FIELDS:
        if profile.get(field_name) in (None, ""):
            missing_fields.append(field_name)

    goal = profile.get("goal")
    if isinstance(goal, str):
        for field_name in GOAL_REQUIRED_FIELDS.get(goal, ()):
            if profile.get(field_name) in (None, ""):
                missing_fields.append(field_name)

    unique_missing_fields = sorted(set(missing_fields))
    return {
        "missing_fields": unique_missing_fields,
        "feasibility_issues": goal_spec.feasibility_issues,
        "feasibility_requires_review": bool(missing_fields) or goal_spec.requires_hitl,
        "hitl_reason": goal_spec.feasibility_message,
    }


# --- New behavior (not a relocation) -----------------------------------------------------
# core/profile/schema.py already defines Profile/Constraints Pydantic models (extra="forbid",
# with range/type constraints) but nothing in the codebase ever actually validated a profile
# against them before this subgraph existed -- only ExtractedProfile was exercised. Wiring
# them in here gives the profile form real reasonableness/type checks (e.g. "age must be
# between 13 and 100") at near-zero cost, since the models already exist.
def validate_profile_schema(profile: dict[str, Any]) -> list[str]:
    """Validate biometric/constraint fields against the Profile/Constraints models."""
    errors: list[str] = []
    profile_fields = {
        key: profile.get(key) for key in ("age", "sex", "height_cm", "current_weight_kg")
    }
    try:
        Profile(**{k: v for k, v in profile_fields.items() if v not in (None, "")})
    except ValidationError as exc:
        errors.extend(_format_validation_errors(exc))

    constraint_fields = {key: profile.get(key) for key in CONSTRAINT_FIELDS}
    try:
        Constraints(**{k: v for k, v in constraint_fields.items() if v not in (None, "")})
    except ValidationError as exc:
        errors.extend(_format_validation_errors(exc))
    return errors


def _format_validation_errors(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    ]


# --- End new behavior ---------------------------------------------------------------------


def _should_skip_profile_extraction(profile: dict[str, Any]) -> bool:
    """Skip LLM extraction when the seed profile is already complete and feasible."""
    goal_spec = derive_goal_spec(profile)
    return not validate_profile_completeness(profile, goal_spec)["feasibility_requires_review"]


def extract_profile(
    query: str,
    profile: dict[str, Any],
    *,
    revision_feedback: str | None = None,
) -> dict[str, Any]:
    """Merge the stored/seed profile with LLM-extracted query fields into a flat profile."""
    if _should_skip_profile_extraction(profile):
        extracted = ExtractedProfile()
    else:
        extraction_query = resolve_extraction_query(query, profile)
        extracted = extract_profile_from_query(extraction_query)
    merged = merge_profile_sources(query=query, profile=profile, extracted=extracted)
    if revision_feedback:
        merged = apply_revision_overrides(merged, revision_feedback)
    return merged


def merge_form_submission(profile: dict[str, Any], submission: dict[str, Any]) -> dict[str, Any]:
    """Merge a submitted profile-form dict into the working profile (submission wins).

    Raw fields only: no derived goal metric is ever written back here. This is the fix for
    the original stale-value bug -- previously this function also recomputed
    weight_delta_kg/weekly_rate_kg/feasibility_level/goal_archetype and stored them in the
    returned profile, so an edit to target_weight_kg alone could leave a stale derived
    weight_delta_kg in place. Now those values are never persisted at all; downstream
    callers get them fresh from `derive_goal_spec(profile)`.
    """
    merged = dict(profile)
    for field_name, value in submission.items():
        if value is not None and value != "":
            merged[field_name] = value
    _normalize_days_per_week(merged)
    return merged


# `persist_profile` is imported directly from `core.shared.profile.store` above; `load_stored_profile`
# is its pre-existing name in this module, kept as an alias so other call sites (e.g. planning)
# don't need to change import paths in this pass.
load_stored_profile = load_run_profile
