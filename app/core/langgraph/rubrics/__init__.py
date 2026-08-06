"""Versioned rubrics, loaded from git.

Rubrics live here rather than in Postgres because a rubric decides what passes.
In a table, someone raises the quads MRV from 22 to
30 with a single UPDATE — no PR, no diff — and every previously issued verify
report becomes unexplainable. In git, that change is a reviewable commit.

Each file carries a ``rubric_version``. A stored verify report records the
version it was produced under, so an old verdict can be reproduced by checking
out the matching commit.

Files are read once at import. They are configuration, not request data.
"""

import json
from pathlib import Path
from typing import Any

_RUBRICS_DIR = Path(__file__).parent


def _load(name: str) -> dict[str, Any]:
    """Read one rubric file.

    Args:
        name: File stem, e.g. ``"macro_rules"``.

    Returns:
        The parsed rubric.
    """
    return json.loads((_RUBRICS_DIR / f"{name}.json").read_text(encoding="utf-8"))


MACRO_RULES = _load("macro_rules")
VOLUME_LANDMARKS = _load("volume_landmarks")
CONTRAINDICATIONS = _load("contraindications")

# All three files must agree, or a report citing one version was produced partly
# under another and cannot be reproduced. Enforced at import so the process
# refuses to start rather than emitting untraceable verdicts.
_VERSIONS = {
    MACRO_RULES["rubric_version"],
    VOLUME_LANDMARKS["rubric_version"],
    CONTRAINDICATIONS["rubric_version"],
}
if len(_VERSIONS) != 1:
    raise RuntimeError(f"rubric versions disagree: {sorted(_VERSIONS)}")

RUBRIC_VERSION: str = MACRO_RULES["rubric_version"]

__all__ = [
    "CONTRAINDICATIONS",
    "MACRO_RULES",
    "RUBRIC_VERSION",
    "VOLUME_LANDMARKS",
]
