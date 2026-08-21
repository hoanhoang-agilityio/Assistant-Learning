"""Typed accessors for request identity stored in runnable configuration."""

from collections.abc import Mapping
from typing import Any


def get_user_id(config: Mapping[str, Any] | None) -> int | None:
    """Extract the user id from runnable metadata.

    Args:
        config: Configuration attached to the current graph run.

    Returns:
        The integer user id, or ``None`` when the run is anonymous.
    """
    value = ((config or {}).get("metadata") or {}).get("user_id")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def get_session_id(config: Mapping[str, Any] | None) -> str:
    """Extract the session id from the checkpointer thread configuration.

    Args:
        config: Configuration attached to the current graph run.

    Returns:
        The checkpointer thread id, or an empty string when absent.
    """
    value = ((config or {}).get("configurable") or {}).get("thread_id", "")
    return value if isinstance(value, str) else ""


__all__ = ["get_session_id", "get_user_id"]
