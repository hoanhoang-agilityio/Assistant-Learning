import json
from pathlib import Path
from typing import Any

from core.vfs import VFS


def load_verification_report(workspace_path: str) -> dict[str, Any]:
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("verify/verification_v1.json"):
        return {"passed": False, "feedback": "missing_verification_report"}
    return json.loads(vfs.read("verify/verification_v1.json"))


def append_supervisor_decision(workspace_path: str, entry: dict[str, Any]) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.append("logs/supervisor_decisions.jsonl", json.dumps(entry) + "\n")
