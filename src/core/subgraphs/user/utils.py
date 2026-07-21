import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.llm.serializers import compact_profile_for_llm
from core.profile.extraction import extract_profile_from_query
from core.profile.goal_spec import assess_goal_feasibility, derive_goal_spec_fields
from core.profile.normalize import _sync_activity_and_days, merge_profile_sources
from core.profile.schema import (
    CONSTRAINT_FIELDS,
    GOAL_REQUIRED_FIELDS,
    REQUIRED_PROFILE_FIELDS,
    Constraints,
    ExtractedProfile,
    Profile,
)
from core.vfs import VFS

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
    """Re-extract plan-change fields from revision text and override the merged profile."""
    stripped = revision_feedback.strip()
    if not stripped:
        return profile
    from core.profile.normalize import normalize_extracted_profile

    extracted = extract_profile_from_query(stripped)
    overrides = normalize_extracted_profile(extracted)
    updated = dict(profile)
    for field_name in REVISION_OVERRIDE_FIELDS:
        value = overrides.get(field_name)
        if value is not None and value != "":
            updated[field_name] = value
    parsed_days = _parse_days_per_week_from_text(stripped)
    if parsed_days is not None:
        updated["days_per_week"] = parsed_days
    _sync_activity_and_days(updated)
    updated.update(derive_goal_spec_fields(updated))
    # Internal signal, popped by `_extract_node`: whether *this* revision text explicitly
    # named a training-frequency target, vs. days_per_week merely being carried over from the
    # prior profile. The Fitness subgraph needs this to know when profile.days_per_week should
    # override edit-derived day counts (see resolve_expected_day_count).
    updated["_days_per_week_explicit"] = (
        parsed_days is not None or overrides.get("days_per_week") is not None
    )
    return updated


def validate_profile_completeness(profile: dict[str, Any]) -> dict[str, Any]:
    """Rule-based completeness + goal-feasibility checks.

    Relocated unchanged from ``planning.utils.validate_profile_data``.
    """
    enriched = {**profile, **derive_goal_spec_fields(profile)}
    missing_fields: list[str] = []
    for field_name in REQUIRED_PROFILE_FIELDS:
        if enriched.get(field_name) in (None, ""):
            missing_fields.append(field_name)

    goal = enriched.get("goal")
    if isinstance(goal, str):
        for field_name in GOAL_REQUIRED_FIELDS.get(goal, ()):
            if enriched.get(field_name) in (None, ""):
                missing_fields.append(field_name)
        if goal in {"fat_loss", "muscle_gain"}:
            has_target = enriched.get("target_weight_kg") not in (None, "")
            has_delta = enriched.get("weight_delta_kg") not in (None, "")
            if not has_target and not has_delta:
                missing_fields.append("target_weight_kg")

    feasibility = assess_goal_feasibility(enriched)
    unique_missing_fields = sorted(set(missing_fields))
    return {
        "missing_fields": unique_missing_fields,
        "feasibility_issues": feasibility.get("issues", []),
        "feasibility_requires_review": bool(missing_fields)
        or feasibility.get("requires_hitl", False),
        "hitl_reason": feasibility.get("message"),
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


def _should_skip_profile_extraction(
    user_profile: dict[str, Any], constraints: dict[str, Any]
) -> bool:
    """Skip LLM extraction when orchestration already has a complete, feasible profile."""
    candidate = {**user_profile, **constraints}
    return not validate_profile_completeness(candidate)["feasibility_requires_review"]


def extract_profile(
    query: str,
    user_profile: dict[str, Any],
    constraints: dict[str, Any],
    *,
    revision_feedback: str | None = None,
) -> dict[str, Any]:
    """Merge stored profile/constraints with LLM-extracted query fields into a flat profile."""
    if _should_skip_profile_extraction(user_profile, constraints):
        extracted = ExtractedProfile()
    else:
        extraction_query = resolve_extraction_query(query, user_profile)
        extracted = extract_profile_from_query(extraction_query)
    profile = merge_profile_sources(
        query=query,
        user_profile=user_profile,
        constraints=constraints,
        extracted=extracted,
    )
    if revision_feedback:
        profile = apply_revision_overrides(profile, revision_feedback)
    return profile


def merge_form_submission(profile: dict[str, Any], submission: dict[str, Any]) -> dict[str, Any]:
    """Merge a submitted profile-form dict into the working profile (submission wins)."""
    merged = dict(profile)
    for field_name, value in submission.items():
        if value is not None and value != "":
            merged[field_name] = value
    _sync_activity_and_days(merged)
    merged.update(derive_goal_spec_fields(merged))
    return merged


def persist_profile(workspace_path: str, profile: dict[str, Any]) -> None:
    """Persist the validated profile snapshot to the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write(
        "plan/profile.json",
        json.dumps(compact_profile_for_llm(profile), indent=2),
    )


def load_stored_profile(workspace_path: str) -> dict[str, Any]:
    """Load the profile snapshot persisted by the User subgraph."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("plan/profile.json"):
        return {}
    return json.loads(vfs.read("plan/profile.json"))
