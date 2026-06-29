import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD
from core.vfs import VFS

FINAL_PLAN_SOURCE = "fitness/final_plan.md"
FINAL_PLAN_DEST = "final/final_plan.md"


def persist_trigger_data(
    verification_passed: bool,
    faithfulness_score: float | None,
    approval_status: str | None,
) -> dict[str, Any]:
    """Return whether PERSIST_RESULTS may run."""
    blocked_reasons: list[str] = []
    if not verification_passed:
        blocked_reasons.append("verification_not_passed")
    if faithfulness_score is None or faithfulness_score < FAITHFULNESS_PASS_THRESHOLD:
        blocked_reasons.append("faithfulness_below_threshold")
    if approval_status != "approved":
        blocked_reasons.append("approval_missing")
    return {
        "can_persist": not blocked_reasons,
        "persist_blocked_reasons": blocked_reasons,
    }


def save_run_data(
    run_id: str,
    thread_id: str,
    orchestration_state: dict[str, Any],
) -> dict[str, Any]:
    workspace_path = orchestration_state["workspace_path"]
    vfs = VFS.for_run(Path(workspace_path))
    snapshot = {
        "run_id": run_id,
        "thread_id": thread_id,
        "query": orchestration_state.get("query"),
        "request_type": orchestration_state.get("request_type"),
        "route_decision": orchestration_state.get("route_decision"),
        "verification_passed": orchestration_state.get("verification_passed"),
        "faithfulness_score": orchestration_state.get("faithfulness_score"),
        "approval_status": orchestration_state.get("approval_status"),
        "persisted_at": datetime.now(UTC).isoformat(),
    }
    vfs.write("logs/run_snapshot.json", json.dumps(snapshot, indent=2))
    return {"run_id": run_id, "snapshot_path": "logs/run_snapshot.json"}


def save_metrics_data(
    run_id: str,
    faithfulness_score: float | None,
    verification_report: dict[str, Any],
) -> dict[str, Any]:
    metrics = {
        "run_id": run_id,
        "faithfulness_score": faithfulness_score,
        "verification_passed": verification_report.get("passed", False),
        "ragas": verification_report.get("ragas", {}),
        "persisted_at": datetime.now(UTC).isoformat(),
    }
    return metrics


def write_metrics_artifact(workspace_path: str, metrics: dict[str, Any]) -> str:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("logs/metrics.json", json.dumps(metrics, indent=2))
    return "logs/metrics.json"


def save_artifacts_data(workspace_path: str) -> dict[str, Any]:
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists(FINAL_PLAN_SOURCE):
        raise FileNotFoundError(f"Missing source artifact: {FINAL_PLAN_SOURCE}")

    draft_plan = vfs.read(FINAL_PLAN_SOURCE)
    vfs.write(FINAL_PLAN_DEST, draft_plan)
    final_artifact_path = str(Path(workspace_path) / FINAL_PLAN_DEST)
    result = {
        "persisted_at": datetime.now(UTC).isoformat(),
        "artifacts": [FINAL_PLAN_DEST],
        "final_artifact_path": final_artifact_path,
    }
    vfs.write("logs/persist_result.json", json.dumps(result, indent=2))
    return result
