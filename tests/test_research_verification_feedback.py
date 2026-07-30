"""L1 Phase 4, Stage B: verification_feedback threading from state through
research/executor.py -> run_research_agent -> _synthesize_findings ->
build_synthesis_llm_extra -> the actual LLM payload. Only set when the Policy
Engine routed here via verification_failed_auto_retry (see
tests/test_supervisor_router.py / test_verification_retry_target.py for the
routing/attribution side). All LLM calls are mocked -- no real API cost."""

import json
from pathlib import Path
from typing import Any

import pytest

from core.capabilities.research import executor as research_executor_module
from core.capabilities.research import research_agent as research_agent_module
from core.capabilities.research.executor import SupervisorRoutedResearchExecutor
from core.capabilities.research.research_agent import _synthesize_findings
from core.capabilities.research.schema import ResearchFindings
from core.capabilities.research.utils import build_synthesis_llm_extra
from core.orchestration.agents.execution_context import build_execution_context
from core.orchestration.graph.run import create_initial_state
from core.shared.profile.goal_spec import derive_goal_spec


class TestBuildSynthesisLlmExtra:
    def test_includes_verification_feedback_when_present(self) -> None:
        extra = build_synthesis_llm_extra(
            sources=[], evidence=[], verification_feedback="Citation issues: X"
        )
        assert extra["verification_feedback"] == "Citation issues: X"

    def test_omits_verification_feedback_when_absent(self) -> None:
        extra = build_synthesis_llm_extra(sources=[], evidence=[])
        assert "verification_feedback" not in extra

    def test_omits_verification_feedback_when_empty_string(self) -> None:
        extra = build_synthesis_llm_extra(sources=[], evidence=[], verification_feedback="")
        assert "verification_feedback" not in extra


class TestSynthesizeFindingsPayload:
    """Verifies the feedback actually reaches the LLM payload, not just an
    intermediate dict -- mocks _invoke_with_node to capture the HumanMessage
    sent, since that's the real integration point."""

    def _fake_findings(self) -> ResearchFindings:
        return ResearchFindings(
            consensus="Stub consensus for a test that doesn't care about content.",
            key_findings=[
                {
                    "claim": "Stub claim for a test that doesn't care about content.",
                    "source_url": "https://example.com/stub",
                }
            ],
            recommended_sources=[],
        )

    def test_payload_includes_feedback_when_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_invoke_with_node(node, schema, messages):
            captured["node"] = node
            captured["payload"] = json.loads(messages[1].content)
            return self._fake_findings()

        monkeypatch.setattr(research_agent_module, "_invoke_with_node", fake_invoke_with_node)

        _synthesize_findings(
            query="q",
            profile={"goal": "fat_loss"},
            goal_spec=derive_goal_spec({"goal": "fat_loss"}),
            sources=[],
            evidence=[],
            verification_feedback="Faithfulness score 0.4 below 0.90",
        )

        assert captured["node"] == "research_synthesis"
        assert captured["payload"]["verification_feedback"] == "Faithfulness score 0.4 below 0.90"

    def test_payload_omits_feedback_key_when_not_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_invoke_with_node(node, schema, messages):
            captured["payload"] = json.loads(messages[1].content)
            return self._fake_findings()

        monkeypatch.setattr(research_agent_module, "_invoke_with_node", fake_invoke_with_node)

        _synthesize_findings(
            query="q",
            profile={"goal": "fat_loss"},
            goal_spec=derive_goal_spec({"goal": "fat_loss"}),
            sources=[],
            evidence=[],
        )

        assert "verification_feedback" not in captured["payload"]


class TestExecutorThreadsFeedbackFromState:
    """Verifies research/executor.py actually reads state["verification_feedback"]
    and passes it through to run_research_agent -- not just that the lower
    layers handle it correctly in isolation."""

    def test_passes_state_verification_feedback_to_run_research_agent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        workspace_root: Path,
        complete_profile: dict[str, Any],
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_run_research_agent(**kwargs):
            captured.update(kwargs)
            from core.capabilities.research.schema import ResearchAgentResult

            return ResearchAgentResult(
                sources=[],
                evidence=[],
                structured_findings=ResearchFindings(
                    consensus="Stub consensus long enough to pass validation.",
                    key_findings=[
                        {
                            "claim": "Stub claim long enough to pass validation.",
                            "source_url": "https://example.com/stub",
                        }
                    ],
                    recommended_sources=[],
                ),
                evidence_summary="stub",
                agent_iterations=1,
            )

        monkeypatch.setattr(research_executor_module, "run_research_agent", fake_run_research_agent)

        state = create_initial_state(
            run_id="research-retry-v1",
            thread_id="research-retry-thread-v1",
            query="Build me a 4-day plan",
            user_profile=complete_profile,
            constraints={"days_per_week": 4, "equipment": "gym"},
            workspace_root=workspace_root,
        )
        state["verification_feedback"] = "Citation issues: no_sources_referenced_in_draft"
        ctx = build_execution_context(intent="build_plan")

        SupervisorRoutedResearchExecutor().execute(state, ctx)

        assert (
            captured["verification_feedback"] == "Citation issues: no_sources_referenced_in_draft"
        )

    def test_passes_none_when_state_has_no_feedback(
        self,
        monkeypatch: pytest.MonkeyPatch,
        workspace_root: Path,
        complete_profile: dict[str, Any],
    ) -> None:
        captured: dict[str, Any] = {}

        def fake_run_research_agent(**kwargs):
            captured.update(kwargs)
            from core.capabilities.research.schema import ResearchAgentResult

            return ResearchAgentResult(
                sources=[],
                evidence=[],
                structured_findings=ResearchFindings(
                    consensus="Stub consensus long enough to pass validation.",
                    key_findings=[
                        {
                            "claim": "Stub claim long enough to pass validation.",
                            "source_url": "https://example.com/stub",
                        }
                    ],
                    recommended_sources=[],
                ),
                evidence_summary="stub",
                agent_iterations=1,
            )

        monkeypatch.setattr(research_executor_module, "run_research_agent", fake_run_research_agent)

        state = create_initial_state(
            run_id="research-first-pass-v1",
            thread_id="research-first-pass-thread-v1",
            query="Build me a 4-day plan",
            user_profile=complete_profile,
            constraints={"days_per_week": 4, "equipment": "gym"},
            workspace_root=workspace_root,
        )
        ctx = build_execution_context(intent="build_plan")

        SupervisorRoutedResearchExecutor().execute(state, ctx)

        assert captured["verification_feedback"] is None
