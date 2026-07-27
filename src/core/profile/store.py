"""Shared VFS-backed profile store: seed, load, split, and persist the run's flat profile."""

import json
from pathlib import Path
from typing import Any

from core.llm.serializers import compact_profile_for_llm
from core.profile.normalize import _normalize_days_per_week, resolve_target_weight
from core.profile.schema import CONSTRAINT_FIELDS
from core.vfs import VFS
from core.vfs.layout import PLAN_PROFILE


def seed_profile(
    workspace_path: str,
    user_profile: dict[str, Any],
    constraints: dict[str, Any],
) -> None:
    """Merge API-supplied profile/constraints into a flat dict and write `plan/profile.json`.

    Mirrors the tail of `merge_profile_sources` (constraints as base, user_profile
    overriding, then raw-field normalization) minus the LLM-extraction step, since no
    query extraction has happened yet at create-run time. Only raw fields are persisted --
    derived goal metrics are never written here; see `core.profile.goal_spec.derive_goal_spec`.
    """
    profile: dict[str, Any] = {}
    for field_name, value in constraints.items():
        if value is not None and value != "":
            profile[field_name] = value
    for field_name, value in user_profile.items():
        if field_name == "missing_fields":
            continue
        if value is not None and value != "":
            profile[field_name] = value
    _normalize_days_per_week(profile)
    resolve_target_weight(profile)
    persist_profile(workspace_path, profile)


def load_run_profile(workspace_path: str) -> dict[str, Any]:
    """Read `plan/profile.json`; return `{}` if it doesn't exist yet."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists(PLAN_PROFILE):
        return {}
    return json.loads(vfs.read(PLAN_PROFILE))


def split_constraints(profile: dict[str, Any]) -> dict[str, Any]:
    """Extract `CONSTRAINT_FIELDS` from a flat profile dict."""
    return {field: profile[field] for field in CONSTRAINT_FIELDS if field in profile}


def persist_profile(workspace_path: str, profile: dict[str, Any]) -> None:
    """Persist the validated profile snapshot to the run workspace VFS (overwrite)."""
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write(PLAN_PROFILE, json.dumps(compact_profile_for_llm(profile), indent=2))
