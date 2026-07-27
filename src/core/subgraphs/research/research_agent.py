"""LLM-driven Research Agent with custom ReAct loop and structured outputs."""

import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from core.config.settings import get_settings
from core.knowledge.ingest import seed_default_corpus
from core.knowledge.retriever import LocalKnowledgeRetriever
from core.llm.budgets import LLM_NODE_BUDGETS
from core.llm.factory import (
    get_standard_llm,
    invoke_bound_llm,
    invoke_standard_structured_output,
)
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.payload import compact_json
from core.profile.goal_spec import GoalSpec
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
    build_eval_llm_extra,
    build_research_context_payload,
    build_synthesis_llm_extra,
    compact_sources_for_llm,
    derive_evidence_summary,
    extract_tavily_data,
    has_sufficient_research_coverage,
    is_local_kb_url,
    load_existing_research,
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
        self.extract_count: int = 0
        self.extracted_urls: set[str] = set()
        self.failed_extract_urls: set[str] = set()
        settings = get_settings()
        self.max_total_searches: int = settings.research_max_total_searches
        self.max_total_extracts: int = settings.research_max_total_extracts
        self.tool_content_preview_chars: int = settings.research_tool_content_preview_chars

    def add_sources(self, sources: list[dict[str, Any]]) -> None:
        self.sources.extend(sources)

    def add_evidence(self, evidence: list[dict[str, Any]]) -> None:
        self.evidence.extend(evidence)
        for item in evidence:
            url = str(item.get("url", ""))
            if url:
                self.extracted_urls.add(url)

    def can_search(self) -> bool:
        return self.search_count < self.max_total_searches

    def record_search(self) -> None:
        self.search_count += 1

    def can_extract(self, url_count: int = 1) -> bool:
        return self.extract_count + url_count <= self.max_total_extracts

    def remaining_extract_slots(self) -> int:
        return max(self.max_total_extracts - self.extract_count, 0)

    def record_extract_attempt(self, urls: list[str]) -> None:
        self.extract_count += len(urls)

    def mark_extract_results(self, urls: list[str], evidence: list[dict[str, Any]]) -> None:
        evidence_urls = {str(item.get("url", "")) for item in evidence if item.get("url")}
        for url in urls:
            if url in evidence_urls:
                self.extracted_urls.add(url)
            else:
                self.failed_extract_urls.add(url)


def _invoke_with_node[T](node: str, schema: type[T], messages: list) -> T:
    token = set_llm_metrics_node(node)
    budget = LLM_NODE_BUDGETS.get(node)
    reasoning_effort_override = budget.reasoning_effort_override if budget else None
    try:
        return invoke_standard_structured_output(
            schema,
            messages,
            prompt_cache_key=node,
            reasoning_effort_override=reasoning_effort_override,
        )
    finally:
        reset_llm_metrics_node(token)


def _plan_search_queries(
    *,
    query: str,
    request_type: str | None,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    execution_plan: ExecutionPlan,
) -> SearchQueryBatch:
    payload = build_research_context_payload(
        query=query,
        request_type=request_type,
        profile=profile,
        goal_spec=goal_spec,
        execution_plan=execution_plan,
    )
    return _invoke_with_node(
        "research_query_planning",
        SearchQueryBatch,
        [
            SystemMessage(content=QUERY_PLANNING_SYSTEM_PROMPT),
            HumanMessage(content=compact_json(payload)),
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
    return compact_json({"planned_search_queries": planned})


def _execute_tool_call(
    tool_name: str,
    tool_args: dict[str, Any],
    session: _ResearchSession,
) -> str:
    if tool_name == "tavily_search":
        if not session.can_search():
            return compact_json(
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
        return compact_json(
            {
                "query": search_query,
                "source_count": len(result["sources"]),
                "sources": compact_sources_for_llm(result["sources"][:5]),
            }
        )
    if tool_name == "tavily_extract":
        urls = tool_args.get("urls", [])
        if not isinstance(urls, list):
            urls = []
        cleaned_urls = [str(url) for url in urls if url and not is_local_kb_url(str(url))]
        urls_to_fetch: list[str] = []
        skipped_urls: list[str] = []
        for url in cleaned_urls:
            if url in session.extracted_urls:
                skipped_urls.append(url)
                continue
            if url in session.failed_extract_urls:
                skipped_urls.append(url)
                continue
            if not session.can_extract():
                break
            urls_to_fetch.append(url)
        if not urls_to_fetch:
            return compact_json(
                {
                    "document_count": 0,
                    "skipped_urls": skipped_urls,
                    "error": "extract_budget_exhausted_or_duplicate"
                    if not session.can_extract()
                    else "no_new_urls",
                    "source_count": len(session.sources),
                }
            )
        session.record_extract_attempt(urls_to_fetch)
        result = extract_tavily_data(urls_to_fetch)
        session.mark_extract_results(urls_to_fetch, result["evidence"])
        session.add_evidence(result["evidence"])
        preview_limit = session.tool_content_preview_chars
        return compact_json(
            {
                "document_count": len(result["evidence"]),
                "failed_urls": [url for url in urls_to_fetch if url in session.failed_extract_urls],
                "evidence": [
                    {
                        "url": item.get("url"),
                        "content_preview": str(item.get("content", ""))[:preview_limit],
                    }
                    for item in result["evidence"]
                ],
            }
        )
    tool = _TOOL_MAP.get(tool_name)
    if tool is None:
        return compact_json({"error": f"Unknown tool: {tool_name}"})
    return str(tool.invoke(tool_args))


def _plan_tavily_calls(
    query_batch: SearchQueryBatch,
    session: _ResearchSession,
    *,
    profile: dict[str, Any],
    retriever: LocalKnowledgeRetriever,
) -> tuple[bool, list[tuple[str, str, list[dict[str, Any]]]]]:
    """Decide which Tavily queries to run, reserving the search budget sequentially.

    session.can_search()/record_search() is a check-then-increment against a
    shared counter and must stay sequential — only the network calls
    themselves (fetched afterward) are safe to parallelize. Returns
    (used_tavily, planned): an ordered list of (query, task, local_documents)
    to fetch. local_documents is attached per query to preserve the existing
    multiplicity (added once per executed query, same as before this
    refactor — post_process_sources dedupes by URL downstream).
    """
    settings = get_settings()
    used_tavily = False
    planned: list[tuple[str, str, list[dict[str, Any]]]] = []

    for task_plan in query_batch.task_plans:
        local_documents = retriever.retrieve_for_task(task=task_plan.task, profile=profile)
        if retriever.has_sufficient_coverage(task=task_plan.task, profile=profile):
            session.add_sources(
                retriever.documents_to_sources(local_documents, task=task_plan.task)
            )
            session.add_evidence(retriever.documents_to_evidence(local_documents))
            continue

        used_tavily = True
        attach_local = local_documents if settings.local_kb_enabled else []
        for search_query in task_plan.queries:
            if not session.can_search():
                return used_tavily, planned
            session.record_search()
            planned.append((search_query, task_plan.task, attach_local))

    return used_tavily, planned


def _fetch_planned_tavily_calls(
    planned: list[tuple[str, str, list[dict[str, Any]]]],
    session: _ResearchSession,
    retriever: LocalKnowledgeRetriever,
) -> None:
    """Run planned Tavily searches concurrently; merge results back in order.

    Each submission gets its own contextvars.Context copy: a bare
    ThreadPoolExecutor does not propagate contextvars (Langfuse's trace-id)
    into worker threads on its own, and a single Context object cannot be
    entered from more than one thread at a time, so each call needs its own
    copy rather than sharing one. Merging into `session` happens back on the
    calling thread after every future resolves, so the mutable session
    accumulator is never touched concurrently.
    """
    if not planned:
        return
    with ThreadPoolExecutor(max_workers=len(planned)) as executor:
        futures = [
            executor.submit(contextvars.copy_context().run, search_tavily_data, search_query)
            for search_query, _task, _local_documents in planned
        ]
        results = [future.result() for future in futures]

    for (_search_query, task_description, local_documents), result in zip(
        planned, results, strict=True
    ):
        session.add_sources(result["sources"])
        if local_documents:
            session.add_sources(
                retriever.documents_to_sources(local_documents, task=task_description)
            )
            session.add_evidence(retriever.documents_to_evidence(local_documents))


def _run_planned_searches(
    query_batch: SearchQueryBatch,
    session: _ResearchSession,
    *,
    profile: dict[str, Any],
) -> bool:
    """Execute planned queries, using local KB first and Tavily only for uncovered tasks.

    Tavily calls within the budget-bounded batch run concurrently — they are
    independent network I/O with no data dependency on each other.

    Returns True when at least one task required Tavily fallback.
    """
    seed_default_corpus()
    retriever = LocalKnowledgeRetriever()
    used_tavily, planned = _plan_tavily_calls(
        query_batch, session, profile=profile, retriever=retriever
    )
    _fetch_planned_tavily_calls(planned, session, retriever)
    return used_tavily


def _has_sufficient_evidence_deterministic(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> bool:
    """Heuristic gate to skip the LLM evidence-evaluation call when coverage looks adequate."""
    return has_sufficient_research_coverage(sources, evidence)


def _evaluate_evidence(
    *,
    query: str,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    execution_plan: ExecutionPlan,
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> EvidenceEvaluation:
    if _has_sufficient_evidence_deterministic(sources, evidence):
        return EvidenceEvaluation(sufficient=True, gaps=[], refined_queries=[])

    payload = build_research_context_payload(
        query=query,
        request_type=None,
        profile=profile,
        goal_spec=goal_spec,
        execution_plan=execution_plan,
        include_task_rationale=False,
        extra=build_eval_llm_extra(sources, evidence),
    )
    return _invoke_with_node(
        "research_evidence_eval",
        EvidenceEvaluation,
        [
            SystemMessage(content=EVALUATION_SYSTEM_PROMPT),
            HumanMessage(content=compact_json(payload)),
        ],
    )


def _run_react_loop(
    *,
    query: str,
    request_type: str | None,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    execution_plan: ExecutionPlan,
    query_batch: SearchQueryBatch,
    session: _ResearchSession,
) -> None:
    settings = get_settings()
    max_iterations = settings.research_max_search_iterations
    # Every iteration resends the growing transcript (system + tools + prior
    # turns) as a new request — the best-shaped automatic-caching candidate
    # in this codebase, since the prefix is byte-identical up to each new
    # turn. A stable prompt_cache_key keeps iterations routed to the same
    # backend cache bucket.
    llm = (
        get_standard_llm()
        .bind_tools(RESEARCH_AGENT_TOOLS)
        .bind(prompt_cache_key="research_react_loop")
    )

    context_payload = build_research_context_payload(
        query=query,
        request_type=request_type,
        profile=profile,
        goal_spec=goal_spec,
    )
    messages: list = [
        SystemMessage(content=REACT_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Research context:\n{compact_json(context_payload)}\n\n"
                "Planned queries (already searched):\n"
                f"{_build_react_initial_message(query_batch)}\n\n"
                "Use tavily_extract on the best URLs from collected sources. "
                "Only call tavily_search for refined follow-up queries if evidence gaps remain."
            )
        ),
    ]

    token = set_llm_metrics_node("research_react_loop")
    try:
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
    finally:
        reset_llm_metrics_node(token)

    evaluation = _evaluate_evidence(
        query=query,
        profile=profile,
        goal_spec=goal_spec,
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


def _synthesize_findings(
    *,
    query: str,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> ResearchFindings:
    payload = build_research_context_payload(
        query=query,
        request_type=None,
        profile=profile,
        goal_spec=goal_spec,
        extra=build_synthesis_llm_extra(sources, evidence),
    )
    return _invoke_with_node(
        "research_synthesis",
        ResearchFindings,
        [
            SystemMessage(content=SYNTHESIS_SYSTEM_PROMPT),
            HumanMessage(content=compact_json(payload)),
        ],
    )


def run_research_agent(
    *,
    query: str,
    request_type: str | None,
    profile: dict[str, Any],
    goal_spec: GoalSpec,
    execution_plan: ExecutionPlan,
    workspace_path: str | None = None,
    is_reresearch: bool = False,
) -> ResearchAgentResult:
    """Execute the full Research Agent pipeline.

    `goal_spec` must be derived by the caller (`_research_agent_node`) from this same
    `profile` -- passed through, never recomputed inside this module.
    """
    if _AGENT_OVERRIDE is not None:
        return _AGENT_OVERRIDE(
            query=query,
            request_type=request_type,
            profile=profile,
            execution_plan=execution_plan,
        )

    session = _ResearchSession()
    skip_tavily = False
    if is_reresearch and workspace_path:
        existing = load_existing_research(workspace_path)
        if existing and has_sufficient_research_coverage(
            existing["sources"],
            existing["evidence"],
        ):
            session.add_sources(existing["sources"])
            session.add_evidence(existing["evidence"])
            skip_tavily = True

    if not skip_tavily:
        query_batch = _plan_search_queries(
            query=query,
            request_type=request_type,
            profile=profile,
            goal_spec=goal_spec,
            execution_plan=execution_plan,
        )
        used_tavily = _run_planned_searches(query_batch, session, profile=profile)
        should_run_react = used_tavily and not has_sufficient_research_coverage(
            session.sources,
            session.evidence,
        )
        if should_run_react:
            _run_react_loop(
                query=query,
                request_type=request_type,
                profile=profile,
                goal_spec=goal_spec,
                execution_plan=execution_plan,
                query_batch=query_batch,
                session=session,
            )

    ranked_sources, merged_evidence = post_process_sources(
        session.sources,
        session.evidence,
        max_extracts_remaining=session.remaining_extract_slots(),
        failed_extract_urls=session.failed_extract_urls,
    )
    structured_findings = _synthesize_findings(
        query=query,
        profile=profile,
        goal_spec=goal_spec,
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
