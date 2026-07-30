"""Loading a run's fitness inputs (profile, plan, research evidence) from the VFS."""

import json
from pathlib import Path
from typing import Any

from core.planning.utils import has_execution_plan, load_execution_plan
from core.profile.store import load_run_profile, split_constraints
from core.vfs import VFS


def load_fitness_context(workspace_path: str) -> dict[str, Any]:
    """Hydrate Fitness's VFS-backed context: profile+constraints, execution plan, research
    findings, and prior verification feedback. `plan/profile.json` stores profile and
    constraint fields together as one flat dict, so `constraints` here is derived via
    `split_constraints` rather than read from a separate artifact.
    """
    vfs = VFS.for_run(Path(workspace_path))
    profile = load_run_profile(workspace_path)
    evidence_summary: str | None = None
    structured_findings: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    verification_feedback: str | None = None
    execution_plan: dict[str, Any] | None = None

    if has_execution_plan(workspace_path):
        execution_plan = load_execution_plan(workspace_path).model_dump()

    if vfs.exists("research/findings.json"):
        findings = json.loads(vfs.read("research/findings.json"))
        structured = findings.get("structured_findings")
        if isinstance(structured, dict) and structured.get("consensus"):
            structured_findings = structured
            evidence_summary = _format_structured_evidence_summary(structured)
        else:
            evidence_summary = findings.get("evidence_summary")
        raw_evidence = findings.get("evidence") or []
        if isinstance(raw_evidence, list):
            evidence = raw_evidence

    if vfs.exists("research/sources.json"):
        raw_sources = json.loads(vfs.read("research/sources.json"))
        if isinstance(raw_sources, list):
            sources = raw_sources

    if vfs.exists("verify/verification_v1.json"):
        verification = json.loads(vfs.read("verify/verification_v1.json"))
        verification_feedback = verification.get("feedback")

    return {
        "profile": profile,
        "constraints": split_constraints(profile),
        "execution_plan": execution_plan,
        "structured_findings": structured_findings,
        "evidence_summary": evidence_summary,
        "evidence": evidence,
        "sources": sources,
        "verification_feedback": verification_feedback,
    }


def _format_structured_evidence_summary(structured: dict[str, Any]) -> str:
    lines = [str(structured.get("consensus", ""))]
    key_findings = structured.get("key_findings") or []
    if key_findings:
        lines.append("")
        lines.append("Key findings:")
        for finding in key_findings:
            if isinstance(finding, dict):
                claim = str(finding.get("claim", "")).strip()
                source_url = str(finding.get("source_url", "")).strip()
                if claim and source_url:
                    lines.append(f"- {claim} ({source_url})")
                elif claim:
                    lines.append(f"- {claim}")
            else:
                lines.append(f"- {finding}")
    return "\n".join(line for line in lines if line)
