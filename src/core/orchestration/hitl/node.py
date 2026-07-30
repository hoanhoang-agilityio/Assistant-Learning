import json
from pathlib import Path
from uuid import uuid4

from core.adapters.vfs import VFS
from core.capabilities.wrapper import merge_subgraph_updates
from core.orchestration.agents.execution_context import CapabilityResult
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.hitl.utils import hitl_control_data, request_approval_data


def invoke_hitl_node(state: OrchestrationState) -> dict:
    """Process HITL interrupt/resume for final approval.

    Reports its own outcome only, via `last_capability_result` -- never sets
    `run_complete` or decides to route to persist itself. The Supervisor's Policy
    Engine (`core.orchestration.routing.policy_engine`'s `_hitl_outcome` rule: approved ->
    persist, rejected -> finish) is the actual deterministic routing.
    """
    if state["approval_status"] == "rejected":
        result = CapabilityResult(
            request_id=uuid4(),
            capability="hitl",
            status="completed",
            summary="User rejected the artifact.",
            artifacts={"approved": False},
        )
        return merge_subgraph_updates(
            state,
            {
                "current_node": "hitl",
                "waiting_for_user": False,
                "last_capability_result": result.model_dump(mode="json"),
            },
            subgraph="hitl",
            steps=["rejected"],
        )

    if state["approval_status"] == "approved":
        result = CapabilityResult(
            request_id=uuid4(),
            capability="hitl",
            status="completed",
            summary="User approved the artifact.",
            artifacts={"approved": True},
        )
        return merge_subgraph_updates(
            state,
            {
                "current_node": "hitl",
                "waiting_for_user": False,
                "last_capability_result": result.model_dump(mode="json"),
            },
            subgraph="hitl",
            steps=["approved"],
        )

    control = hitl_control_data(
        waiting_for_user=state["waiting_for_user"],
        approval_status=state["approval_status"],
        user_response=state["user_response"],
    )
    updates: dict = {"current_node": "hitl", **control}

    if control.get("waiting_for_user") is False:
        return merge_subgraph_updates(state, updates, subgraph="hitl", steps=["resume"])

    vfs = VFS.for_run(Path(state["workspace_path"]))
    draft_plan = ""
    verification_report: dict = {"passed": state["verification_passed"]}
    if vfs.exists("fitness/final_plan.md"):
        draft_plan = vfs.read("fitness/final_plan.md")
    if vfs.exists("verify/verification_v1.json"):
        verification_report = json.loads(vfs.read("verify/verification_v1.json"))
    approval = request_approval_data(draft_plan, verification_report)
    updates.update(approval)
    updates["waiting_for_user"] = True
    return merge_subgraph_updates(state, updates, subgraph="hitl", steps=["approval_request"])
