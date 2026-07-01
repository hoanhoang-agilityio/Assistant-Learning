"""LLM-driven Research Agent with custom ReAct loop and structured outputs."""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from core.config.settings import get_settings
from core.llm.factory import (
    get_standard_llm,
    invoke_bound_llm,
    invoke_standard_structured_output,
)
from core.subgraphs.planning.schema import ExecutionPlan
from core.subgraphs.research.prompts import (
    EVALUATION_SYSTEM_PROMPT,
    QUERY_PLANNING_SYSTEM_PROMPT,
    REACT_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)
from core.subgraphs.research.schema import (
    EvidenceEvaluation,
    ResearchAgentResult,
    ResearchFindings,
    SearchQueryBatch,
)
from core.subgraphs.research.tools import RESEARCH_AGENT_TOOLS
from core.subgraphs.research.utils import (
    derive_evidence_summary,
    extract_tavily_data,
    post_process_sources,
    search_tavily_data,
)

ResearchAgentOverride = Callable[..., ResearchAgentResult]

_AGENT_OVERRIDE: ResearchAgentOverride | None = None

_TOOL_MAP = {tool.name: tool for tool in RESEARCH_AGENT_TOOLS}


def configure_research_agent(override: ResearchAgentOverride | None) -> None:
    """Override the research agent (used in tests)."""
    global _AGENT_OVERRIDE
    _AGENT_OVERRIDE = override


class _ResearchSession:
    """Mutable accumulator for sources and evidence during agent execution."""

    def __init__(self) -> None:
        self.sources: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.iterations: int = 0
        self.search_count: int = 0
        self.max_total_searches: int = get_settings().research_max_total_searches

    def add_sources(self, sources: list[dict[str, Any]]) -> None:
        self.sources.extend(sources)

    def add_evidence(self, evidence: list[dict[str, Any]]) -> None:
        self.evidence.extend(evidence)

    def can_search(self) -> bool:
        return self.search_count < self.max_total_searches

    def record_search(self) -> None:
        self.search_count += 1


def _plan_search_queries(
    *,
    query: str,
    request_type: str | None,
    profile: dict[str, Any],
    execution_plan: ExecutionPlan,
) -> SearchQueryBatch:
    payload = {
        "query": query,
        "request_type": request_type,
        "profile": profile,
        "plan_rationale": execution_plan.plan_rationale,
        "tasks": [task.model_dump() for task in execution_plan.tasks],
    }
    return invoke_standard_structured_output(
        SearchQueryBatch,
        [
            SystemMessage(content=QUERY_PLANNING_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ],
    )


def _build_react_initial_message(query_batch: SearchQueryBatch) -> str:
    planned = [
        {
            "task_order": plan.task_order,
            "task": plan.task,
            "queries": plan.queries,
        }
        for plan in query_batch.task_plans
    ]
    return json.dumps({"planned_search_queries": planned}, indent=2)


def _execute_tool_call(
    tool_name: str,
    tool_args: dict[str, Any],
    session: _ResearchSession,
) -> str:
    if tool_name == "tavily_search":
        if not session.can_search():
            return json.dumps(
                {
                    "error": "search_budget_exhausted",
                    "message": "Maximum Tavily search calls reached for this run.",
                    "source_count": len(session.sources),
                }
            )
        search_query = str(tool_args.get("query", ""))
        session.record_search()
        result = search_tavily_data(search_query)
        session.add_sources(result["sources"])
        return json.dumps(
            {
                "query": search_query,
                "source_count": len(result["sources"]),
                "sources": result["sources"][:5],
            }
        )
    if tool_name == "tavily_extract":
        urls = tool_args.get("urls", [])
        if not isinstance(urls, list):
            urls = []
        result = extract_tavily_data([str(url) for url in urls])
        session.add_evidence(result["evidence"])
        return json.dumps(
            {
                "document_count": len(result["evidence"]),
                "evidence": [
                    {
                        "url": item.get("url"),
                        "content_preview": str(item.get("content", ""))[:500],
                    }
                    for item in result["evidence"]
                ],
            }
        )
    tool = _TOOL_MAP.get(tool_name)
    if tool is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return str(tool.invoke(tool_args))


def _run_planned_searches(query_batch: SearchQueryBatch, session: _ResearchSession) -> None:
    """Execute planned queries once, respecting the global search budget."""
    for task_plan in query_batch.task_plans:
        for search_query in task_plan.queries:
            if not session.can_search():
                return
            session.record_search()
            result = search_tavily_data(search_query)
            session.add_sources(result["sources"])


def _run_react_loop(
    *,
    query: str,
    request_type: str | None,
    profile: dict[str, Any],
    execution_plan: ExecutionPlan,
    query_batch: SearchQueryBatch,
    session: _ResearchSession,
) -> None:
    settings = get_settings()
    max_iterations = settings.research_max_search_iterations
    llm = get_standard_llm().bind_tools(RESEARCH_AGENT_TOOLS)

    context_payload = {
        "query": query,
        "request_type": request_type,
        "profile": profile,
        "plan_rationale": execution_plan.plan_rationale,
        "tasks": [task.model_dump() for task in execution_plan.tasks],
    }
    messages: list = [
        SystemMessage(content=REACT_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Research context:\n{json.dumps(context_payload, indent=2)}\n\n"
                "Planned queries (already searched):\n"
                f"{_build_react_initial_message(query_batch)}\n\n"
                "Use tavily_extract on the best URLs from collected sources. "
                "Only call tavily_search for refined follow-up queries if evidence gaps remain."
            )
        ),
    ]

    for iteration in range(max_iterations):
        session.iterations = iteration + 1
        response = invoke_bound_llm(
            llm,
            messages,
            model_name=settings.openai_standard_model,
        )
        if not isinstance(response, AIMessage):
            break

        messages.append(response)
        tool_calls = response.tool_calls or []
        if not tool_calls:
            break

        for tool_call in tool_calls:
            tool_result = _execute_tool_call(
                tool_call["name"],
                tool_call.get("args", {}),
                session,
            )
            messages.append(
                ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_call["id"],
                )
            )

    evaluation = _evaluate_evidence(
        query=query,
        profile=profile,
        execution_plan=execution_plan,
        sources=session.sources,
        evidence=session.evidence,
    )
    if evaluation.sufficient or not evaluation.refined_queries or not session.can_search():
        return

    for refined_query in evaluation.refined_queries:
        if not session.can_search():
            break
        session.record_search()
        result = search_tavily_data(refined_query)
        session.add_sources(result["sources"])


def _evaluate_evidence(
    *,
    query: str,
    profile: dict[str, Any],
    execution_plan: ExecutionPlan,
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> EvidenceEvaluation:
    payload = {
        "query": query,
        "profile": profile,
        "tasks": [task.model_dump() for task in execution_plan.tasks],
        "source_count": len(sources),
        "sources_preview": sources[:10],
        "evidence_preview": [
            {
                "url": item.get("url"),
                "content_preview": str(item.get("content", ""))[:300],
            }
            for item in evidence[:5]
        ],
    }
    return invoke_standard_structured_output(
        EvidenceEvaluation,
        [
            SystemMessage(content=EVALUATION_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ],
    )


def _synthesize_findings(
    *,
    query: str,
    profile: dict[str, Any],
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> ResearchFindings:
    payload = {
        "query": query,
        "profile": profile,
        "sources": sources[:15],
        "evidence": [
            {
                "url": item.get("url"),
                "content": str(item.get("content", ""))[:1500],
            }
            for item in evidence[:8]
        ],
    }
    return invoke_standard_structured_output(
        ResearchFindings,
        [
            SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(payload, indent=2)),
        ],
    )


def run_research_agent(
    *,
    query: str,
    request_type: str | None,
    profile: dict[str, Any],
    execution_plan: ExecutionPlan,
) -> ResearchAgentResult:
    """Execute the full Research Agent pipeline."""
    if _AGENT_OVERRIDE is not None:
        return _AGENT_OVERRIDE(
            query=query,
            request_type=request_type,
            profile=profile,
            execution_plan=execution_plan,
        )

    session = _ResearchSession()
    query_batch = _plan_search_queries(
        query=query,
        request_type=request_type,
        profile=profile,
        execution_plan=execution_plan,
    )

    _run_planned_searches(query_batch, session)

    _run_react_loop(
        query=query,
        request_type=request_type,
        profile=profile,
        execution_plan=execution_plan,
        query_batch=query_batch,
        session=session,
    )

    ranked_sources, merged_evidence = post_process_sources(session.sources, session.evidence)
    structured_findings = _synthesize_findings(
        query=query,
        profile=profile,
        sources=ranked_sources,
        evidence=merged_evidence,
    )
    evidence_summary = derive_evidence_summary(structured_findings)

    return ResearchAgentResult(
        sources=ranked_sources,
        evidence=merged_evidence,
        structured_findings=structured_findings,
        evidence_summary=evidence_summary,
        agent_iterations=session.iterations,
    )
