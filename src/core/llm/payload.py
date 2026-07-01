"""Utilities for compacting LLM request payloads."""

import json
from typing import Any


def strip_empty_values(value: Any) -> Any:
    """Recursively remove null, empty string, empty list, and empty dict values."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            stripped = strip_empty_values(item)
            if stripped is None:
                continue
            if isinstance(stripped, str) and not stripped:
                continue
            if isinstance(stripped, (list, dict)) and not stripped:
                continue
            cleaned[key] = stripped
        return cleaned
    if isinstance(value, list):
        cleaned_list = [strip_empty_values(item) for item in value]
        return [
            item
            for item in cleaned_list
            if item is not None and item != "" and item != [] and item != {}
        ]
    return value


def compact_json(payload: Any) -> str:
    """Serialize payload as compact JSON with empty values removed."""
    cleaned = strip_empty_values(payload)
    return json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)


def limit_feedback_items(feedback: list[str], max_items: int = 5) -> list[str]:
    """Deduplicate and cap feedback strings for LLM retry payloads."""
    limited: list[str] = []
    for item in feedback:
        normalized = item.strip()
        if not normalized or normalized in limited:
            continue
        limited.append(normalized)
        if len(limited) >= max_items:
            break
    return limited
