import json
from pathlib import Path

import pytest

from core.persist.utils import (
    persist_trigger_data,
    save_artifacts_data,
    save_metrics_data,
    save_run_data,
)
from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD
from core.vfs import VFS


def test_persist_trigger_blocks_without_approval() -> None:
    # persist_trigger_data called directly -- the @tool wrapper (agents.tools.persist_trigger)
    # was removed in the User Subgraph refactor's cleanup pass since it was never bound to an
    # LLM/agent; persist/node.py already called persist_trigger_data directly in production.
    result = persist_trigger_data(
        verification_passed=True,
        faithfulness_score=0.95,
        approval_status="pending",
    )
    assert result["can_persist"] is False
    assert "approval_missing" in result["persist_blocked_reasons"]


def test_persist_trigger_blocks_low_faithfulness() -> None:
    result = persist_trigger_data(
        verification_passed=True,
        faithfulness_score=0.5,
        approval_status="pending",
    )
    assert result["can_persist"] is False
    assert "faithfulness_below_threshold" in result["persist_blocked_reasons"]


def test_persist_trigger_blocks_missing_faithfulness_score() -> None:
    """A capability that never ran the faithfulness check (checks are chosen
    per-request via the verification capability's payload, not a fixed global
    strategy) still reports faithfulness_below_threshold as a diagnostic
    reason -- it's informational, not a hard gate, since approval_status is
    the only thing that actually blocks persist (see persist_trigger_data
    above and core.subgraphs.fitness.capability._after_verification)."""
    result = persist_trigger_data(
        verification_passed=True,
        faithfulness_score=None,
        approval_status="pending",
    )
    assert "faithfulness_below_threshold" in result["persist_blocked_reasons"]
    assert "approval_missing" in result["persist_blocked_reasons"]


def test_persist_trigger_allows_approved_despite_failed_verification() -> None:
    result = persist_trigger_data(
        verification_passed=False,
        faithfulness_score=0.5,
        approval_status="approved",
    )
    assert result["can_persist"] is True
    assert result["persist_blocked_reasons"] == []


def test_persist_trigger_allows_happy_path() -> None:
    result = persist_trigger_data(
        verification_passed=True,
        faithfulness_score=FAITHFULNESS_PASS_THRESHOLD,
        approval_status="approved",
    )
    assert result["can_persist"] is True
    assert result["persist_blocked_reasons"] == []


def test_save_run_writes_snapshot(tmp_path: Path) -> None:
    workspace_path = tmp_path / "run_snapshot"
    workspace_path.mkdir()
    orchestration_state = {
        "workspace_path": str(workspace_path),
        "query": "test query",
        "execution_context": {"intent": "build_plan", "response_mode": "plan"},
        "verification_passed": True,
        "faithfulness_score": 0.95,
        "approval_status": "approved",
    }
    result = save_run_data("run-1", "thread-1", orchestration_state)
    vfs = VFS.for_run(workspace_path)
    assert result["snapshot_path"] == "logs/run_snapshot.json"
    snapshot = json.loads(vfs.read("logs/run_snapshot.json"))
    assert snapshot["run_id"] == "run-1"
    assert snapshot["query"] == "test query"
    assert snapshot["intent"] == "build_plan"
    assert snapshot["response_mode"] == "plan"


def test_save_metrics_returns_structured_payload() -> None:
    report = {"passed": True, "ragas": {"faithfulness_score": 0.95, "pass_fail": True}}
    metrics = save_metrics_data("run-1", 0.95, report)
    assert metrics["faithfulness_score"] == 0.95
    assert metrics["verification_passed"] is True


def test_save_artifacts_copies_final_plan(tmp_path: Path) -> None:
    workspace_path = tmp_path / "run_artifacts"
    workspace_path.mkdir()
    vfs = VFS.for_run(workspace_path)
    vfs.write("fitness/final_plan.md", "# Final draft plan")

    result = save_artifacts_data(str(workspace_path))

    assert vfs.exists("final/final_plan.md")
    assert vfs.exists("logs/persist_result.json")
    assert result["final_artifact_path"].endswith("final/final_plan.md")
    assert vfs.read("final/final_plan.md") == "# Final draft plan"


def test_save_artifacts_raises_when_draft_missing(tmp_path: Path) -> None:
    workspace_path = tmp_path / "run_missing"
    workspace_path.mkdir()
    with pytest.raises(FileNotFoundError):
        save_artifacts_data(str(workspace_path))
