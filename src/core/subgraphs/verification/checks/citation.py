"""Citation check: does the draft actually reference the sources research gathered?"""

from typing import Any


def citation_check_data(draft_plan: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not draft_plan.strip():
        return {
            "passed": False,
            "issues": ["missing_draft_plan"],
            "cited_source_count": 0,
        }

    # No sources gathered is a real grounding failure, not "nothing to check" --
    # `not sources` used to make `passed` true unconditionally here, silently
    # rubber-stamping a plan built on zero research evidence.
    if not sources:
        return {
            "passed": False,
            "issues": ["no_sources_gathered"],
            "cited_source_count": 0,
        }

    cited_source_count = 0
    issues: list[str] = []
    for source in sources:
        url = str(source.get("url", ""))
        title = str(source.get("title", ""))
        provider = str(source.get("provider", ""))
        if url and (
            url in draft_plan or (provider == "local_kb" and title.lower() in draft_plan.lower())
        ):
            cited_source_count += 1
            continue
        if title and title.lower() in draft_plan.lower():
            cited_source_count += 1

    # No keyword rubber-stamp: synthesis always emits a "## Evidence Summary"
    # section, so a bare "evidence"/"research" substring match here used to
    # count as citing a source regardless of whether any real source was
    # actually referenced. cited_source_count now only reflects genuine
    # URL/title matches against the sources actually gathered.
    if cited_source_count == 0:
        issues.append("no_sources_referenced_in_draft")

    passed = not issues
    return {
        "passed": passed,
        "issues": issues,
        "cited_source_count": cited_source_count,
    }
