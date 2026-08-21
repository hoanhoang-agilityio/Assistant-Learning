"""Shared response builders for supervisor tools."""

import json
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from app.core.langgraph.verification.scoring import sort_issues
from app.schemas.graph import MissingFields, ToolRefusal
from app.services.profile import FIELD_LABELS


def _result(
    tool_call_id: str, payload: dict[str, Any], update: dict[str, Any] | None = None
) -> Command:
    """Return a tool result, optionally with a state update alongside it."""
    body = dict(payload)
    issues = body.get("issues")
    if isinstance(issues, list):
        body["issues"] = [
            {
                "severity": issue["severity"],
                "location": issue["location"],
                "message": issue["message"],
                "rubric_ref": issue["rubric_ref"],
            }
            for issue in sort_issues(issues)
        ]
    return Command(
        update={
            **(update or {}),
            "messages": [
                ToolMessage(
                    content=json.dumps(body, ensure_ascii=False, default=str),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


def _refuse(
    tool_call_id: str, refusal: MissingFields | ToolRefusal, missing: list[str] | None = None
) -> Command:
    """Return a refusal the supervisor can act on."""
    body: dict[str, Any] = dict(refusal)
    if missing:
        body["ask_for"] = [FIELD_LABELS.get(field, field) for field in missing]
    return Command(
        update={
            **({"missing_fields": missing} if missing else {}),
            "messages": [
                ToolMessage(
                    content=json.dumps(body, ensure_ascii=False),
                    tool_call_id=tool_call_id,
                    status="error",
                )
            ],
        }
    )


__all__ = ["_refuse", "_result"]
