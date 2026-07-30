"""Backwards-compatible re-exports for the old research.utils module.

This file used to hold 539 lines spanning six unrelated concerns, including the
Tavily transport calls sitting directly among the domain helpers. The logic now
lives in modules named after what they do:

    context.py      loading profile / execution plan / prior findings from the VFS
    guidelines.py   local knowledge-base retrieval and hit -> source/evidence shaping
    payloads.py     the compacted LLM payloads for the eval and synthesis calls
    tavily.py       the web search/extract adapter -- the only module that talks
                    to the Tavily transport
    sources.py      dedupe, verify, rank, compress and summarise gathered sources
    artifacts.py    persisting research results to the VFS

Nothing was rewritten in the move. This shim exists so existing importers keep
working; prefer importing from the modules above in new code.
"""

from core.subgraphs.research.artifacts import write_research_artifacts
from core.subgraphs.research.context import (
    load_execution_plan_for_research,
    load_existing_research,
    load_profile_for_research,
)
from core.subgraphs.research.guidelines import (
    guideline_hits_to_evidence,
    guideline_hits_to_sources,
    has_sufficient_research_coverage,
    is_local_kb_url,
    search_guideline_documents,
)
from core.subgraphs.research.payloads import (
    build_eval_llm_extra,
    build_goal_context,
    build_research_context_payload,
    build_synthesis_llm_extra,
    compact_source_for_llm,
    compact_sources_for_llm,
)
from core.subgraphs.research.sources import (
    dedupe_sources_by_url,
    derive_evidence_summary,
    post_process_sources,
)
from core.subgraphs.research.tavily import (
    extract_tavily_data,
    normalize_extract_results,
    normalize_search_results,
    search_tavily_data,
)

__all__ = [
    "build_eval_llm_extra",
    "build_goal_context",
    "build_research_context_payload",
    "build_synthesis_llm_extra",
    "compact_source_for_llm",
    "compact_sources_for_llm",
    "dedupe_sources_by_url",
    "derive_evidence_summary",
    "extract_tavily_data",
    "guideline_hits_to_evidence",
    "guideline_hits_to_sources",
    "has_sufficient_research_coverage",
    "is_local_kb_url",
    "load_execution_plan_for_research",
    "load_existing_research",
    "load_profile_for_research",
    "normalize_extract_results",
    "normalize_search_results",
    "post_process_sources",
    "search_guideline_documents",
    "search_tavily_data",
    "write_research_artifacts",
]
