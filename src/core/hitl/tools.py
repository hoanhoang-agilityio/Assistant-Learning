from langchain_core.tools import BaseTool, tool

from core.hitl.utils import (
    request_approval_data,
    request_clarification_data,
)


@tool
def request_clarification(missing_fields: list[str], context: str) -> dict:
    """Request user clarification for missing profile or ambiguous goal."""
    return request_clarification_data(missing_fields, context)


@tool
def request_approval(draft_plan: str, verification_report: dict) -> dict:
    """Request user approval before final plan persistence."""
    return request_approval_data(draft_plan, verification_report)


HITL_TOOLS: list[BaseTool] = [
    request_clarification,
    request_approval,
]
