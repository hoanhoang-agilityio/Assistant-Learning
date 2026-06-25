from langchain_core.tools import BaseTool, tool


@tool
def request_clarification(missing_fields: list[str], context: str) -> dict:
    """Request user clarification for missing profile or ambiguous goal."""
    ...


@tool
def request_approval(draft_plan: str, verification_report: dict) -> dict:
    """Request user approval before final plan persistence."""
    ...


HITL_TOOLS: list[BaseTool] = [
    request_clarification,
    request_approval,
]
