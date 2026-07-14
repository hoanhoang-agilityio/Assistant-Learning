import json
from pathlib import Path

from core.agents.state import OrchestrationState
from core.hitl.utils import hitl_control_data, request_approval_data
from core.vfs import VFS


def invoke_hitl_node(state: OrchestrationState) -> dict:
    """Process HITL interrupt/resume for clarification or final approval."""
    if state["approval_status"] == "rejected":
        return {
            "current_node": "hitl",
            "waiting_for_user": False,
            "approval_status": "rejected",
            "hitl_type": None,
        }

    if state["approval_status"] == "approved":
        return {
            "current_node": "hitl",
            "waiting_for_user": False,
            "approval_status": "approved",
            "hitl_type": None,
        }

    if not state["waiting_for_user"] and state.get("route_decision") == "REPLAN":
        return {
            "current_node": "hitl",
            "waiting_for_user": False,
        }

    control = hitl_control_data(
        waiting_for_user=state["waiting_for_user"],
        approval_status=state["approval_status"],
        user_response=state["user_response"],
    )
    updates: dict = {"current_node": "hitl", **control}

    if control.get("waiting_for_user") is False:
        return updates

    if state["route_decision"] == "COMPLETE" or state["verification_passed"]:
        vfs = VFS.for_run(Path(state["workspace_path"]))
        draft_plan = ""
        verification_report: dict = {"passed": state["verification_passed"]}
        if vfs.exists("fitness/final_plan.md"):
            draft_plan = vfs.read("fitness/final_plan.md")
        if vfs.exists("verify/verification_v1.json"):
            verification_report = json.loads(vfs.read("verify/verification_v1.json"))
        approval = request_approval_data(draft_plan, verification_report)
        updates.update(approval)
        return updates

    # NOTE: there used to be a branch here checking state["user_profile"]["missing_fields"]
    # to trigger a "clarification" HITL prompt via request_clarification. Profile
    # completeness is now handled entirely by the User subgraph (interrupt()-based form)
    # before this node is ever reached -- user_profile never carries a missing_fields key
    # anymore, so that branch was unreachable dead code. See core.subgraphs.user.

    updates["approval_status"] = state["approval_status"] or "pending"
    updates["waiting_for_user"] = True
    return updates
