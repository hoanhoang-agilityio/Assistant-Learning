"""Map what the user said onto a stored plan version.

The only LLM involvement in the revert branch, and it is deliberately narrow:
the model picks an id from a list it was given, and every id it can return
already exists. It cannot construct one.

Returning ``None`` is a supported outcome, not a failure.
Asking "which one did you mean?" costs the user one turn; restoring the
wrong plan costs them the plan they were on, and they may not notice until they
train the wrong session.
"""

from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.core.logging import logger
from app.core.prompts import load_resolve_version_prompt
from app.schemas.graph import VersionRef
from app.services.llm.service import llm_service

_RESOLVER_MODEL = "gpt-5-mini"


class VersionChoice(BaseModel):
    """Structured output of the version resolver."""

    version_id: str | None = Field(
        default=None,
        description="Exact version_id from the list, or null when not confident",
    )
    reason: str = Field(
        default="", description="One short phrase naming which version was matched and why"
    )


def render_versions(index: list[VersionRef]) -> str:
    """Render the version index for the prompt and for the user.

    Args:
        index: Version refs, newest first.

    Returns:
        One line per version, the newest marked as current.
    """
    if not index:
        return "No saved versions."

    lines = []
    for position, ref in enumerate(index):
        marker = "  (current)" if position == 0 else ""
        lines.append(f"- {ref['version_id']} · {ref['label']} · saved {ref['created_at']}{marker}")
    return "\n".join(lines)


async def resolve_version_id(query: str, index: list[VersionRef]) -> tuple[str | None, str]:
    """Choose which stored version the user means.

    Args:
        query: What the user said.
        index: Their version refs, newest first.

    Returns:
        ``(version_id, reason)``. ``version_id`` is ``None`` when the request is
        ambiguous or the model returned an id that is not in the index — a
        hallucinated id must never reach a database lookup.
    """
    if not index:
        return None, "no saved versions"
    if len(index) == 1:
        # Only one version exists, and it is the plan they already have. There
        # is nothing to go back to, and the caller reports that.
        return None, "only the current version exists"

    try:
        choice = await llm_service.call(
            [
                HumanMessage(
                    content=load_resolve_version_prompt(
                        versions=render_versions(index), query=query
                    )
                )
            ],
            model_name=_RESOLVER_MODEL,
            response_format=VersionChoice,
        )
    except Exception as e:
        logger.exception("version_resolution_failed", error=str(e))
        return None, "could not work out which version"

    known = {ref["version_id"] for ref in index}
    if choice.version_id not in known:
        if choice.version_id is not None:
            logger.warning("version_resolution_returned_unknown_id", proposed=choice.version_id)
        return None, choice.reason or "ambiguous"

    if choice.version_id == index[0]["version_id"]:
        # The user's current plan. Restoring it would create a duplicate version
        # and change nothing, so it is treated as nothing to do.
        return None, "that is the plan you already have"

    logger.info("version_resolved", version_id=choice.version_id, reason=choice.reason)
    return choice.version_id, choice.reason


def describe_verification_reason(stored_hash: str, current_hash: str) -> str:
    """Explain whether an old assessment still applies to the user.

    ``Uses the profile hash to *skip* re-verification
    when nothing relevant changed. Here the verifiers run either way — they are
    pure functions over data already in memory, so skipping them saves nothing
    measurable — and the hash is used for the part that does matter: telling the
    user whether the checks that passed when they approved this plan still
    describe them.

    Args:
        stored_hash: Profile fingerprint from when the version was saved.
        current_hash: Fingerprint of the profile now.

    Returns:
        A short phrase for the composed answer.
    """
    if stored_hash and stored_hash == current_hash:
        return "Your details are unchanged since this version was saved, so the same checks apply."
    return (
        "Your details have changed since this version was saved, so it was checked again "
        "against your current profile."
    )


def snapshot_to_state(version: Any) -> dict[str, Any]:
    """Map a stored version row onto the fields the pipeline expects.

    Args:
        version: A ``PlanVersion`` row.

    Returns:
        ``{"draft_plan", "macros_at_save", "profile_hash", "rubric_version"}``.
    """
    return {
        "draft_plan": dict(version.plan),
        "macros_at_save": dict(version.macros),
        "profile_hash": version.profile_hash,
        "rubric_version": version.rubric_version,
    }


__all__ = [
    "VersionChoice",
    "describe_verification_reason",
    "render_versions",
    "resolve_version_id",
    "snapshot_to_state",
]
