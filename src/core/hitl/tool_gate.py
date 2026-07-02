from typing import Any

from core.hitl.interrupt_policy import request_tool_approval_data, tool_requires_interrupt


def evaluate_tool_interrupt(
    tool_name: str,
    *,
    used_sensitive_write: bool,
    approved_tools: list[str] | None,
    preview: dict[str, Any],
) -> dict[str, Any] | None:
    """Return HITL updates when a sensitive tool needs user approval."""
    if not used_sensitive_write:
        return None
    if not tool_requires_interrupt(tool_name):
        return None
    if tool_name in (approved_tools or []):
        return None
    return request_tool_approval_data(tool_name, preview)
