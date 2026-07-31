"""Persisting research results into the run VFS."""

import json
import logging
from pathlib import Path
from typing import Any

from core.adapters.vfs import VFS
from core.capabilities.research.schema import ResearchFindings

logger = logging.getLogger(__name__)


def write_research_artifacts(
    workspace_path: str,
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    structured_findings: ResearchFindings,
    evidence_summary: str,
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("research/sources.json", json.dumps(sources, indent=2))
    vfs.write(
        "research/findings.json",
        json.dumps(
            {
                "structured_findings": structured_findings.model_dump(),
                "evidence": evidence,
                "evidence_summary": evidence_summary,
                "source_count": len(sources),
                "local_source_count": sum(
                    1 for source in sources if source.get("provider") == "local_kb"
                ),
            },
            indent=2,
        ),
    )
