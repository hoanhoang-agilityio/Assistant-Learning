"""Deterministic Verification capability executor.

Implements `core.capabilities.executor.CapabilityExecutor`. Swappable via
`configure_verification_executor` for a future LLM-driven ReAct executor that
chooses checks itself, without touching `capability.py`, the dispatcher, or
the graph.
"""

from __future__ import annotations

from uuid import UUID, uuid4

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


def _request_id(state: OrchestrationState) -> UUID:
    pending = state.get("pending_request")
    if pending:
        return UUID(pending["request_id"])
    return uuid4()


class DeterministicVerificationExecutor:
    """Runs exactly the checks the requesting capability asked for -- a fixed
    policy over `pending_request.payload["checks"]`, no reasoning about which
    checks matter."""

    def execute(self, state: OrchestrationState, ctx: ExecutionContext) -> CapabilityResult:
        workspace = state["workspace_path"]
        pending = state.get("pending_request") or {}
        payload = pending.get("payload", {})
        requested_checks = payload.get("checks") or ["consistency", "safety"]
        context = load_verification_context(workspace)
        checks: dict = {}
        if "citation" in requested_checks:
            checks["citation"] = citation_check_data(context["draft_plan"], context["sources"])
        if "consistency" in requested_checks:
            checks["consistency"] = consistency_check_data(
                context["draft_plan"],
                context["macro_targets"],
                context["training_plan"],
                context["plan_blueprint"],
            )
        if "safety" in requested_checks:
            checks["safety"] = safety_check_data(
                context["draft_plan"],
                context["safety_flags"],
                fitness_safety_passed=context.get("fitness_safety_passed"),
            )
        if "faithfulness" in requested_checks:
            grounded_text = context.get("grounded_claims") or ""
            checks["ragas"] = evaluate_faithfulness(
                grounded_text,
                context["evidence"],
                query=state.get("query", ""),
                use_real=_production_use_real_ragas(),
            )
        report = build_verification_report_for_checks(checks)
        write_verification_artifacts(
            workspace_path=workspace,
            verification_report=report,
            ragas=report.get("ragas"),
        )
        return CapabilityResult(
            request_id=_request_id(state),
            capability="verification",
            status="completed",
            output={
                "passed": report.get("passed", False),
                "feedback": report.get("feedback"),
                "faithfulness_score": (report.get("ragas") or {}).get("faithfulness_score"),
                "checks_run": list(checks),
            },
        )


class SupervisorRoutedVerificationExecutor:
    """AgentResult-only Verification executor for the hybrid Supervisor routing
    design (see docs/reports plan). Runs the same fixed 4-check policy as
    `DeterministicVerificationExecutor` -- the old `pending_request.payload["checks"]`
    channel doesn't exist anymore (there's no caller-supplied payload once
    capabilities stop constructing their own handoffs), and in practice every
    caller always requested the same full set, so this executor always runs it."""

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
