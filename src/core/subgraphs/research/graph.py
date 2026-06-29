from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.agents.state import OrchestrationState
from core.subgraphs.research.state import ResearchState
from core.subgraphs.research.tools import (
    rank_sources,
    retrieve_documents,
    search_evidence,
    verify_sources,
)
from core.subgraphs.research.utils import (
    build_evidence_summary,
    build_research_questions,
    load_todos_for_research,
    write_research_artifacts,
)


def _todos_gate_node(state: ResearchState) -> dict:
    todos = load_todos_for_research(state["workspace_path"])
    if not todos:
        return {
            "todos": [],
            "research_questions": [],
            "blocked_by_todos": True,
            "evidence_summary": "Research blocked: plan/todos.json is required before retrieval",
        }

    return {
        "todos": todos,
        "research_questions": build_research_questions(state["query"], todos),
        "blocked_by_todos": False,
    }


def _search_evidence_node(state: ResearchState) -> dict:
    result = search_evidence.invoke(
        {
            "research_questions": state["research_questions"],
            "todos": state["todos"],
        }
    )
    return {"sources": result["sources"]}


def _retrieve_documents_node(state: ResearchState) -> dict:
    source_ids = [source["source_id"] for source in state["sources"][:5]]
    result = retrieve_documents.invoke(
        {
            "source_ids": source_ids,
            "sources": state["sources"],
        }
    )
    return {"evidence": result["evidence"]}


def _rank_sources_node(state: ResearchState) -> dict:
    result = rank_sources.invoke({"sources": state["sources"]})
    return {"sources": result["sources"]}


def _verify_sources_node(state: ResearchState) -> dict:
    result = verify_sources.invoke({"sources": state["sources"]})
    evidence_summary = build_evidence_summary(result["sources"], state["evidence"])
    return {
        "sources": result["sources"],
        "evidence_summary": evidence_summary,
    }


def _write_artifacts_node(state: ResearchState) -> dict:
    write_research_artifacts(
        workspace_path=state["workspace_path"],
        sources=state["sources"],
        evidence=state["evidence"],
        evidence_summary=state["evidence_summary"] or "",
    )
    return {}


def _blocked_node(state: ResearchState) -> dict:
    return {"evidence_summary": state["evidence_summary"]}


def _route_after_todos_gate(state: ResearchState) -> str:
    if state["blocked_by_todos"]:
        return "blocked"
    return "search_evidence"


def build_research_subgraph() -> CompiledStateGraph:
    """Compile the Research subgraph StateGraph."""
    graph = StateGraph(ResearchState)
    graph.add_node("todos_gate", _todos_gate_node)
    graph.add_node("search_evidence", _search_evidence_node)
    graph.add_node("retrieve_documents", _retrieve_documents_node)
    graph.add_node("rank_sources", _rank_sources_node)
    graph.add_node("verify_sources", _verify_sources_node)
    graph.add_node("write_artifacts", _write_artifacts_node)
    graph.add_node("blocked", _blocked_node)
    graph.add_edge(START, "todos_gate")
    graph.add_conditional_edges(
        "todos_gate",
        _route_after_todos_gate,
        {
            "blocked": "blocked",
            "search_evidence": "search_evidence",
        },
    )
    graph.add_edge("search_evidence", "retrieve_documents")
    graph.add_edge("retrieve_documents", "rank_sources")
    graph.add_edge("rank_sources", "verify_sources")
    graph.add_edge("verify_sources", "write_artifacts")
    graph.add_edge("write_artifacts", END)
    graph.add_edge("blocked", END)
    return graph.compile()


@lru_cache
def get_research_subgraph() -> CompiledStateGraph:
    return build_research_subgraph()


def to_research_state(state: OrchestrationState) -> ResearchState:
    return ResearchState(
        query=state["query"],
        request_type=state["request_type"],
        workspace_path=state["workspace_path"],
        todos=[],
        research_questions=[],
        evidence=[],
        sources=[],
        evidence_summary=None,
        blocked_by_todos=False,
    )


def invoke_research_subgraph(state: OrchestrationState) -> dict:
    """Run the Research subgraph and map results back to orchestration updates."""
    result = get_research_subgraph().invoke(to_research_state(state))
    return {
        "current_node": "research",
        "waiting_for_user": result["blocked_by_todos"],
    }


class ResearchGraph:
    """LangGraph graph for Research subgraph."""

    def __init__(self) -> None:
        self._graph = get_research_subgraph()

    def invoke(self, state: ResearchState) -> ResearchState:
        return self._graph.invoke(state)

    def invoke_from_orchestration(self, state: OrchestrationState) -> dict:
        return invoke_research_subgraph(state)
