"""Verification capability executor.

Implements `core.capabilities.executor.CapabilityExecutor`. Swappable via
`configure_verification_executor` for a future LLM-driven ReAct executor that
chooses checks itself, without touching `capability.py`, the dispatcher, or
the graph.
"""

from __future__ import annotations

from uuid import uuid4

from core.agents.execution_context import CapabilityResult, ExecutionContext
from core.agents.state import OrchestrationState
from core.capabilities.executor import CapabilityExecutor
from core.config.settings import get_settings
from core.subgraphs.verification.utils import (
    build_verification_report_for_checks,
    citation_check_data,
    consistency_check_data,
    evaluate_faithfulness,
    load_verification_context,
    safety_check_data,
    write_verification_artifacts,
)


def _production_use_real_ragas() -> bool:
    """settings.verification_production_use_real_ragas, not
    settings.verification_use_real_ragas -- that flag only ever gated the
    offline benchmark (see ragas_benchmark.py) and defaults True; this one is
    the actual production gate, off by default, and deliberately a separate
    setting so benchmark-only runs never accidentally flip production's real
    request behavior. Read fresh on every call (not cached at import) so
    tests/deploys can toggle it without a process restart. See
    docs/reports/known_limitations_remediation_plan.md, L1 (Phase 3)."""
    return get_settings().verification_production_use_real_ragas


class SupervisorRoutedVerificationExecutor:
    """AgentResult-only Verification executor for the hybrid Supervisor routing
    design (see docs/reports plan). Runs a fixed 4-check policy -- every caller
    always requests the same full set, so this executor always runs it."""

    _CHECKS = ("consistency", "safety", "citation", "faithfulness")

    def execute(self, state: OrchestrationState, ctx: ExecutionContext) -> CapabilityResult:
        workspace = state["workspace_path"]
        context = load_verification_context(workspace)
        checks: dict = {
            "citation": citation_check_data(context["draft_plan"], context["sources"]),
            "consistency": consistency_check_data(
                context["draft_plan"],
                context["macro_targets"],
                context["training_plan"],
                context["plan_blueprint"],
            ),
            "safety": safety_check_data(
                context["draft_plan"],
                context["safety_flags"],
                fitness_safety_passed=context.get("fitness_safety_passed"),
            ),
            "ragas": evaluate_faithfulness(
                context.get("grounded_claims") or "",
                context["evidence"],
                query=state.get("query", ""),
                use_real=_production_use_real_ragas(),
            ),
        }
        report = build_verification_report_for_checks(checks)
        write_verification_artifacts(
            workspace_path=workspace,
            verification_report=report,
            ragas=report.get("ragas"),
        )
        return CapabilityResult(
            request_id=uuid4(),
            capability="verification",
            status="completed",
            summary="Verification complete.",
            artifacts={
                "passed": report.get("passed", False),
                "faithfulness_score": (report.get("ragas") or {}).get("faithfulness_score"),
                "retry_target": report.get("retry_target"),
            },
            metadata={"feedback": report.get("feedback"), "checks_run": list(checks)},
        )


_executor: CapabilityExecutor = SupervisorRoutedVerificationExecutor()


def configure_verification_executor(executor: CapabilityExecutor | None) -> None:
    """Override the Verification capability executor (used in tests, or to
    swap in a future ReAct agent)."""
    global _executor
    _executor = executor or SupervisorRoutedVerificationExecutor()


def get_verification_executor() -> CapabilityExecutor:
    return _executor
