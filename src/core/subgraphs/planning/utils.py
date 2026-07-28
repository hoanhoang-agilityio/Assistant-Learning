import json
from pathlib import Path

from core.llm.serializers import compact_profile_for_llm
from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.user.utils import load_stored_profile
from core.vfs import VFS

__all__ = [
    "compact_profile_for_llm",
    "has_execution_plan",
    "load_execution_plan",
    "load_stored_profile",
    "persist_revision_feedback",
    "load_revision_feedback",
]


def persist_revision_feedback(workspace_path: str, feedback: str) -> None:
    """Persist user revision feedback for a Fitness revision resume."""
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("plan/revision_feedback.json", json.dumps({"feedback": feedback.strip()}, indent=2))


def load_revision_feedback(workspace_path: str) -> str | None:
    """Load user revision feedback from the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("plan/revision_feedback.json"):
        return None
    payload = json.loads(vfs.read("plan/revision_feedback.json"))
    feedback = payload.get("feedback")
    if not isinstance(feedback, str):
        return None
    stripped = feedback.strip()
    return stripped or None


def has_execution_plan(workspace_path: str) -> bool:
    """Return whether a canonical execution plan exists on the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    return vfs.exists("plan/execution_plan.json")


def load_execution_plan(workspace_path: str) -> ExecutionPlan:
    """Load the canonical execution plan from the run workspace VFS."""
    vfs = VFS.for_run(Path(workspace_path))
    raw = json.loads(vfs.read("plan/execution_plan.json"))
    return ExecutionPlan.model_validate(raw)
