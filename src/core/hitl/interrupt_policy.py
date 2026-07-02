"""Per-tool HITL interrupt policy for sensitive write operations."""

from typing import Any

# Tools that mutate user-derived state and should pause for approval when invoked.
TOOL_HITL_INTERRUPT_ON: dict[str, bool] = {
    "extract_profile": True,
    "generate_plan": False,
    "validate_profile": False,
    "calculate_macros": False,
    "synthesize_plan": False,
}


def tool_requires_interrupt(tool_name: str) -> bool:
    """Return True when a tool is configured for pre-execution HITL approval."""
    return TOOL_HITL_INTERRUPT_ON.get(tool_name, False)


def request_tool_approval_data(
    tool_name: str,
    preview: dict[str, Any],
) -> dict[str, Any]:
    """Build orchestration updates for a pending per-tool approval interrupt."""
    return {
        "waiting_for_user": True,
        "approval_status": "pending",
        "hitl_type": "tool_approval",
        "pending_tool": tool_name,
        "hitl_message": (
            f"Review extracted profile data before continuing ({tool_name}). "
            f"Approve to proceed or reject to stop the run."
        ),
        "tool_preview": preview,
    }
