"""Persisting verification results into the run VFS."""

import json
from pathlib import Path
from typing import Any

from core.vfs import VFS


def write_verification_artifacts(
    workspace_path: str,
    verification_report: dict[str, Any],
    ragas: dict[str, Any] | None,
) -> None:
    """`ragas` is None when the requesting capability didn't include "faithfulness" in
    its requested checks -- written as JSON null, an honest record that the check simply
    didn't run, not that it ran and failed."""
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("verify/verification_v1.json", json.dumps(verification_report, indent=2))
    vfs.write("verify/ragas.json", json.dumps(ragas, indent=2))
