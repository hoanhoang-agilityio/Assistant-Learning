import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.mcp.tavily_client import TavilyMCPClient, configure_tavily_client
from core.subgraphs.research.agent import ResearchAgent
from core.subgraphs.research.graph import build_research_subgraph, invoke_research_subgraph
from core.subgraphs.research.state import ResearchState
from core.subgraphs.research.tools import rank_sources, search_evidence, verify_sources
from core.subgraphs.research.utils import ResearchTodosGateError, search_evidence_data
from core.vfs import VFS
from tests.helpers.planning import seed_execution_plan


@pytest.fixture(autouse=True)
def reset_tavily_client() -> None:
    configure_tavily_client(None)
    yield
    configure_tavily_client(None)


@pytest.fixture
def mock_tavily_client() -> TavilyMCPClient:
    def search(query: str) -> dict[str, Any]:
        return {
            "results": [
                {
                    "title": f"Evidence for {query}",
                    "url": "https://example.edu/fitness-training",
                    "content": "hypertrophy training evidence",
                    "score": 0.92,
                },
                {
                    "title": "Generic page",
                    "url": "https://example.com/page",
                    "content": "unrelated content",
                    "score": 0.2,
                },
            ]
        }

    def extract(urls: list[str]) -> dict[str, Any]:
        return {
            "results": [{"url": url, "raw_content": f"Document body for {url}"} for url in urls]
        }

    client = TavilyMCPClient(search=search, extract=extract)
    configure_tavily_client(client)
    return client


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "target_weight_kg": 75.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
    }


@pytest.fixture
def research_state(
    workspace_root: Path,
    complete_profile: dict[str, Any],
    mock_tavily_client: TavilyMCPClient,
) -> ResearchState:
    del mock_tavily_client
    initial = create_initial_state(
        run_id="research-run",
        thread_id="research-thread",
        query="I want to lose weight with strength training.",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    seed_execution_plan(initial["workspace_path"], complete_profile)
    return ResearchState(
        query=initial["query"],
        request_type="fat_loss",
        workspace_path=initial["workspace_path"],
        todos=[],
        research_questions=[],
        evidence=[],
        sources=[],
        evidence_summary=None,
        blocked_by_todos=False,
    )


def test_search_evidence_blocked_without_todos(mock_tavily_client: TavilyMCPClient) -> None:
    del mock_tavily_client
    with pytest.raises(ResearchTodosGateError):
        search_evidence_data(["macro evidence"], [])


def test_search_evidence_delegates_to_tavily(mock_tavily_client: TavilyMCPClient) -> None:
    del mock_tavily_client
    result = search_evidence.invoke(
        {
            "research_questions": ["Research hypertrophy evidence"],
            "todos": ["Gather hypertrophy evidence"],
        }
    )
    assert len(result["sources"]) == 2
    assert result["sources"][0]["provider"] == "tavily"


def test_rank_sources_orders_by_score() -> None:
    sources = [
        {"source_id": "a", "score": 0.4},
        {"source_id": "b", "score": 0.9},
    ]
    result = rank_sources.invoke({"sources": sources})
    assert result["sources"][0]["source_id"] == "b"
    assert result["sources"][0]["rank"] == 1


def test_verify_sources_marks_fitness_relevance() -> None:
    sources = [
        {"title": "Training study", "url": "https://example.com", "snippet": "hypertrophy"},
        {"title": "Other", "url": "https://example.com/other", "snippet": "finance"},
    ]
    result = verify_sources.invoke({"sources": sources})
    assert result["sources"][0]["verified"] is True
    assert result["sources"][1]["verified"] is False


def test_research_subgraph_blocked_without_planning_todos(
    workspace_root: Path,
    mock_tavily_client: TavilyMCPClient,
) -> None:
    del mock_tavily_client
    initial = create_initial_state(
        run_id="blocked-run",
        thread_id="blocked-thread",
        query="Need evidence",
        workspace_root=workspace_root,
    )
    orchestration_state: OrchestrationState = {
        **initial,
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
    }
    updates = invoke_research_subgraph(orchestration_state)
    assert updates["waiting_for_user"] is True
    vfs = VFS.for_run(Path(initial["workspace_path"]))
    assert vfs.exists("research/sources.json") is False


def test_research_subgraph_writes_vfs_artifacts(research_state: ResearchState) -> None:
    graph = build_research_subgraph()
    graph.invoke(research_state)
    vfs = VFS.for_run(Path(research_state["workspace_path"]))
    assert vfs.exists("research/sources.json")
    assert vfs.exists("research/findings.json")
    sources = json.loads(vfs.read("research/sources.json"))
    findings = json.loads(vfs.read("research/findings.json"))
    assert len(sources) >= 2
    assert findings["source_count"] == len(sources)
    assert "verified" in findings["evidence_summary"]


def test_research_agent_runs_from_orchestration(research_state: ResearchState) -> None:
    orchestration_state: OrchestrationState = {
        "run_id": "research-run",
        "thread_id": "research-thread",
        "current_node": "supervisor",
        "query": research_state["query"],
        "user_profile": {},
        "constraints": {},
        "request_type": research_state["request_type"],
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "route_decision": None,
        "retry_count": 0,
        "replan_count": 0,
        "verification_passed": False,
        "faithfulness_score": None,
        "waiting_for_user": False,
        "approval_status": None,
        "user_response": None,
        "workspace_path": research_state["workspace_path"],
        "final_artifact_path": None,
    }
    agent = ResearchAgent()
    updates = agent.run(orchestration_state)
    assert updates["current_node"] == "research"
    vfs = VFS.for_run(Path(research_state["workspace_path"]))
    assert vfs.exists("research/findings.json")
