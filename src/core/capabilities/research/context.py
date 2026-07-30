"""Loading a run's research inputs (profile, execution plan, prior findings) from the VFS."""

import json
import logging
from pathlib import Path
from typing import Any

from core.shared.planning.schema import ExecutionPlan
from core.shared.planning.utils import (
    has_execution_plan,
    load_execution_plan,
)
from core.shared.profile.store import load_run_profile
from core.vfs import VFS

logger = logging.getLogger(__name__)


def load_profile_for_research(workspace_path: str) -> dict[str, Any]:
    """Load validated profile from planning VFS artifacts."""
    return load_run_profile(workspace_path)


def load_execution_plan_for_research(workspace_path: str) -> ExecutionPlan | None:
    if not has_execution_plan(workspace_path):
        return None
    return load_execution_plan(workspace_path)


def load_existing_research(workspace_path: str) -> dict[str, Any] | None:
    """Load prior research artifacts when a partial rerun re-enters Research."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("research/sources.json"):
        return None
    sources = json.loads(vfs.read("research/sources.json"))
    evidence: list[dict[str, Any]] = []
    if vfs.exists("research/findings.json"):
        findings_payload = json.loads(vfs.read("research/findings.json"))
        evidence = findings_payload.get("evidence") or []
    return {"sources": sources, "evidence": evidence}
