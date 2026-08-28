"""Rendering of state values into the data blocks a prompt carries."""

import json
from typing import Any

COMPACT_SEPARATORS = (",", ":")


def as_prompt_json(value: Any) -> str | None:
    """Render a profile, plan or verification result as compact JSON, or None when it is empty."""

    if not value:
        return None
    return json.dumps(
        value, sort_keys=True, default=str, separators=COMPACT_SEPARATORS
    )
