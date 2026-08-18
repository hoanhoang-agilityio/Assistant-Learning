"""Tools owned by the QA agent."""

import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from app.core.logging import logger
from app.services.knowledge import knowledge_service
from app.services.nutrition import calc_macros

_DEFAULT_SESSIONS = 3


@tool
def estimate_macros(
    runtime: ToolRuntime,
    sessions_per_week: int | None = None,
    weight_kg: float | None = None,
    goal: str | None = None,
) -> str:
    """Estimate nutrition targets for a hypothetical change."""
    profile = dict(runtime.state.get("profile") or {})
    if weight_kg is not None:
        profile["weight_kg"] = weight_kg

    assumed_goal = goal or profile.get("goal") or "general_health"
    sessions = sessions_per_week or profile.get("days_per_week") or _DEFAULT_SESSIONS

    try:
        macros = calc_macros(profile, sessions_per_week=int(sessions), goal=assumed_goal)
    except (KeyError, ValueError) as e:
        # A missing field is an ordinary outcome here, not a failure: QA has no
        # profile gate in front of it by design, so the honest answer is the
        # general form plus a request for the number.

        return (
            "Not enough is known to estimate this. Answer in the general per-kg form "
            f"and ask for what is missing ({e})."
        )

    return json.dumps(
        {
            "estimate": True,
            "note": (
                "A hypothetical, not the user's current targets. Present it as an estimate "
                "and name the assumptions below."
            ),
            "assumptions": {
                "sessions_per_week": int(sessions),
                "weight_kg": profile.get("weight_kg"),
                "goal": assumed_goal,
            },
            "macros": macros,
        },
        ensure_ascii=False,
    )


@tool
async def search_knowledge(query: str, top_k: int = 4) -> list[dict]:
    """Search the training and nutrition knowledge base.

    Only for answering general knowledge questions. Never use it to retrieve
    data for building or assessing a plan — that data comes from the catalog and
    the rubrics, through the graph, not through this tool.
    """
    passages = await knowledge_service.search(query, top_k=top_k)
    logger.info("search_knowledge_called", query=query, top_k=top_k, results=len(passages))
    return [passage.model_dump() for passage in passages]


__all__ = ["estimate_macros", "search_knowledge"]
