"""The draft store: plan content the supervisor can point at but never retype.

The single most important mechanic in the supervisor architecture
(``docs/supervisor-architecture.md`` §9). Without it, plan JSON travels out of a
tool result, through the supervisor's context, and back into the next tool call
— and the moment a model retypes a number, the guarantee that the plan a user is
given is the plan that was verified is gone.

So a plan-producing tool returns a **handle**. The content stays here, keyed by
that handle, and ``save_plan`` reads it back out. The model can describe a draft
and it can choose between drafts; it cannot author one.

Five rules, all load-bearing:

1. ``commit_draft`` is the only writer. Nothing else in the codebase calls
   :func:`mint`.
2. ``save_plan(draft_id)`` reads content from here, never from its arguments —
   which is why it has no ``plan`` parameter at all.
3. A draft with ``verdict == "fail"`` is refused at save time, not only when the
   answer is composed.
4. Drafts expire. A ``draft_id`` from three turns ago describes a profile that
   may have changed since, and re-verifying at save time would be a second
   verdict the user never saw.
5. ``plan_rendered`` is for prose. The supervisor describes the plan from it; it
   does not reconstruct the plan out of it.

In process and in memory, deliberately. A draft is turn-scoped working state,
not a user's data: nothing here is worth surviving a restart, and a draft that
does survive one has almost certainly outlived the profile it was built for.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from cachetools import TTLCache

from app.core.logging import logger
from app.schemas.graph import DraftEnvelope, Issue, Verdict

# How long a handle stays valid. Long enough for a user to read a plan, think,
# and answer the confirm question; short enough that a `draft_id` scrolled far
# up the conversation cannot be saved against a profile that has since moved.
DRAFT_TTL_SECONDS = 30 * 60

# A ceiling, not a policy: entries leave by TTL. It only bounds memory when many
# sessions are drafting at once.
_MAX_DRAFTS = 1024


@dataclass(frozen=True)
class Draft:
    """One verified plan, held by handle until it is saved or expires.

    Everything ``save_plan`` needs to write a ``plan_versions`` row is here, so
    the save reads no argument the model supplied. ``profile_hash`` and
    ``rubric_version`` are captured at mint time on purpose: they record what
    this plan was checked *against*, and recomputing them at save time would
    stamp the row with a profile the verdict never saw.
    """

    draft_id: str
    plan: dict[str, Any]
    macros: dict[str, Any]
    issues: list[Issue]
    verdict: Verdict
    plan_rendered: str
    profile_hash: str
    rubric_version: str
    diff: dict[str, Any] | None = None
    # Set when this draft's content came out of an older version. Recorded on
    # the saved row so the user can undo an undo — and they will.
    restored_from: str | None = None
    parent_id: str | None = None


_drafts: TTLCache[str, Draft] = TTLCache(maxsize=_MAX_DRAFTS, ttl=DRAFT_TTL_SECONDS)


def mint(
    plan: dict[str, Any],
    macros: dict[str, Any],
    issues: list[Issue],
    verdict: Verdict,
    plan_rendered: str,
    profile_hash: str,
    rubric_version: str,
    diff: dict[str, Any] | None = None,
    restored_from: str | None = None,
    parent_id: str | None = None,
) -> Draft:
    """Store a verified plan and return its handle.

    Called from ``commit_draft`` and from nowhere else. A second caller would be
    a second path to a ``draft_id``, and ``save_plan`` trusts the handle
    precisely because only one function can produce one.

    Args:
        plan: The assembled plan JSON.
        macros: Targets computed for that plan. Never ``None`` — every draft
            carries macros, which is the invariant that replaces the old
            ``calc_macro`` bottleneck.
        issues: Findings from the verification graph, plus any notes the
            producing tool added.
        verdict: The verification verdict.
        plan_rendered: The plan as text, for the supervisor to describe.
        profile_hash: Fingerprint of the profile it was checked against.
        rubric_version: Rubric version the verdict was produced under.
        diff: What this would change, or ``None`` for a build.
        restored_from: The version this content came from, for a restore.
        parent_id: The version this one supersedes.

    Returns:
        The stored draft, whose ``draft_id`` is the only thing that leaves.
    """
    draft = Draft(
        draft_id=str(uuid.uuid4()),
        plan=plan,
        macros=macros,
        issues=issues,
        verdict=verdict,
        plan_rendered=plan_rendered,
        profile_hash=profile_hash,
        rubric_version=rubric_version,
        diff=diff,
        restored_from=restored_from,
        parent_id=parent_id,
    )
    _drafts[draft.draft_id] = draft
    logger.info(
        "draft_minted",
        draft_id=draft.draft_id,
        verdict=verdict,
        issues=len(issues),
        days=len(plan.get("days") or []),
    )
    return draft


def read(draft_id: str) -> Draft | None:
    """Look up a draft by handle.

    Args:
        draft_id: The handle a tool returned earlier this conversation.

    Returns:
        The draft, or ``None`` when the handle is unknown or has expired.
        ``None`` is an ordinary outcome, not an error: the caller tells the user
        the draft went stale and offers to rebuild it.
    """
    draft = _drafts.get(draft_id)
    if draft is None:
        logger.info("draft_not_found", draft_id=draft_id)
    return draft


def expire(draft_id: str) -> None:
    """Drop a draft that has been saved or superseded.

    Not required for correctness — the TTL would collect it — but a saved draft
    that can still be saved again is a way to write the same version twice.

    Args:
        draft_id: The handle to drop.
    """
    _drafts.pop(draft_id, None)


def envelope(draft: Draft) -> DraftEnvelope:
    """Describe a draft to the supervisor without handing over its content.

    The plan appears only as ``plan_rendered`` — prose to describe, not JSON to
    copy. Macros and findings are structured because the supervisor genuinely
    reasons over them: whether to offer a save, and what to say about a warning.

    Args:
        draft: The stored draft.

    Returns:
        The envelope to return as the tool result.
    """
    return DraftEnvelope(
        status="draft",
        draft_id=draft.draft_id,
        plan_rendered=draft.plan_rendered,
        macros=draft.macros,
        issues=draft.issues,
        verdict=draft.verdict,
        diff=draft.diff,
    )


def clear() -> None:
    """Empty the store.

    For tests. Nothing in the application calls this: drafts leave by TTL or by
    :func:`expire`.
    """
    _drafts.clear()


__all__ = ["DRAFT_TTL_SECONDS", "Draft", "clear", "envelope", "expire", "mint", "read"]
