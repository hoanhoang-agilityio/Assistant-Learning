"""Compute macros for a plan and score it against the rubrics — together.

One function, called from every tool body that produces or assesses a plan. That
is not tidiness; it is the replacement for a guarantee the old root graph got
from its topology (``docs/supervisor-architecture.md`` §11.1). There, no path
from a plan to an answer could skip ``calc_macro`` because ``calc_macro`` was the
only edge into ``verification``. Here the two are bundled into one call, so a
tool that scores a plan without computing its macros would have to go out of its
way to do so — and the test suite asserts that none does.

Verification is three pure functions called in sequence, not a subgraph. The
fan-out it used to be bought nothing: the checks are arithmetic over dicts with
no I/O, so running them "concurrently" on one event loop only paid for a
conditional entry edge, an ``add`` reducer and a join node. What the subgraph
enforced structurally — the verifier cannot see the build transcript — survives
in a stronger form here, because :func:`score` takes a plan and a profile and
there is no argument a transcript could be passed as.

Giving a model any part of rubric scoring would make MRV and MEV negotiable.
They are not, which is why none of this is a tool.
"""

from typing import Any

from app.core.langgraph.checks import check_injury, check_macro, check_volume
from app.core.logging import logger
from app.schemas.graph import Issue, Verdict, VerifyScope
from app.services.catalog import load_catalog
from app.services.nutrition import calc_macros
from app.services.rubrics import contraindications, macro_rules, volume_landmarks

_DEFAULT_GOAL = "general_health"

# An empty scope means "assess everything". Used by build_plan, change_plan and
# revert, where all three verifiers are mandatory — only `check` lets the user's
# wording narrow it.
_ALL_SCOPES: tuple[VerifyScope, ...] = ("macro", "volume", "injury")

# A single blocking finding fails the plan. Warnings never do: they are judgment
# calls the user is entitled to overrule, and treating them as failures would
# spend the repair budget on things that were never wrong.
_SEVERITY_ORDER = {"block": 0, "warn": 1, "info": 2}


def sessions_for(plan: dict[str, Any], profile: dict[str, Any]) -> int:
    """Count the sessions a week this plan actually trains.

    Counted off the plan rather than read from the profile, because the profile
    holds what was *asked for*: a slot with no legal exercise leaves a day out,
    and the count that feeds TDEE has to be the one the user will train.

    Args:
        plan: The plan being assessed.
        profile: The user's profile, used only when the plan has no days.

    Returns:
        Sessions per week.
    """
    return len(plan.get("days") or []) or int(profile.get("days_per_week") or 3)


def verify_macro(computed_macros: dict[str, Any], profile: dict[str, Any]) -> list[Issue]:
    """Assess nutrition targets against the macro rubric.

    Args:
        computed_macros: The targets :func:`calc_macros` produced.
        profile: The user's profile. Reads ``weight_kg`` and ``sex``.

    Returns:
        Everything this check found, empty when the targets pass.
    """
    issues = check_macro(computed_macros, profile, macro_rules())
    _log("macro", issues)
    return issues


def verify_volume(plan: dict[str, Any], catalog: dict[str, Any]) -> list[Issue]:
    """Assess weekly volume, frequency and session length.

    Args:
        plan: The plan being assessed.
        catalog: Exercises keyed by ``exercise_id``, for the per-muscle
            contributions the set count is weighted by.

    Returns:
        Everything this check found, empty when the plan passes.
    """
    issues = check_volume(plan, catalog, volume_landmarks())
    _log("volume", issues)
    return issues


def verify_injury(
    plan: dict[str, Any], profile: dict[str, Any], catalog: dict[str, Any]
) -> list[Issue]:
    """Assess the plan against the user's declared injuries.

    Args:
        plan: The plan being assessed.
        profile: The user's profile. Reads ``injuries``.
        catalog: Exercises keyed by ``exercise_id``, for the joint actions and
            loaded positions the contraindication rules match on.

    Returns:
        Everything this check found, empty when the plan passes.
    """
    issues = check_injury(plan, profile, catalog, contraindications())
    _log("injury", issues)
    return issues


def run_checks(
    plan: dict[str, Any],
    profile: dict[str, Any],
    computed_macros: dict[str, Any],
    catalog: dict[str, Any],
    scope: list[VerifyScope] | None = None,
) -> tuple[list[Issue], Verdict]:
    """Run the enabled rubric checks and reduce their findings to a verdict.

    Issues are returned in the order the checks ran, not sorted. Ordering is
    presentation, applied by the consumer through :func:`sort_issues`.

    Args:
        plan: The plan to assess.
        profile: The user's profile.
        computed_macros: The targets computed for this plan.
        catalog: Exercises keyed by ``exercise_id``.
        scope: Which checks to run. ``None`` or empty means all three.

    Returns:
        ``(issues, verdict)``.
    """
    enabled = _enabled_scopes(scope)
    issues: list[Issue] = []

    if "macro" in enabled:
        issues.extend(verify_macro(computed_macros, profile))
    if "volume" in enabled:
        issues.extend(verify_volume(plan, catalog))
    if "injury" in enabled:
        issues.extend(verify_injury(plan, profile, catalog))

    verdict = _verdict_for(issues)
    logger.info(
        "verification_verdict",
        verdict=verdict,
        scope=list(enabled),
        issue_count=len(issues),
        blocking=sum(1 for issue in issues if issue["severity"] == "block"),
    )
    return issues, verdict


async def score(
    plan: dict[str, Any],
    profile: dict[str, Any],
    scope: list[VerifyScope] | None = None,
) -> tuple[dict[str, Any], list[Issue], Verdict]:
    """Compute this plan's macros and run the enabled rubric checks over both.

    Stays a coroutine although nothing here awaits: every caller is an async
    tool body, and the catalog and rubric loads behind it are database reads
    that are cached rather than genuinely synchronous.

    Args:
        plan: The plan to score.
        profile: The user's profile. Every required field is present by the time
            this runs — the profile precondition on the calling tool saw to that.
        scope: Which verifiers to run. ``None`` or empty means all three, which
            is mandatory for anything that could be saved; only a read-only
            review lets the user's wording narrow it.

    Returns:
        ``(macros, issues, verdict)``. ``macros`` is never empty, which is the
        invariant every draft envelope depends on.

    Raises:
        KeyError: When a required profile field is absent, which means a tool
            ran its body without its precondition passing.
    """
    macros = calc_macros(
        profile,
        sessions_per_week=sessions_for(plan, profile),
        goal=profile.get("goal", _DEFAULT_GOAL),
    )

    issues, verdict = run_checks(plan, profile, macros, load_catalog(), scope)
    logger.info(
        "plan_scored", verdict=verdict, issues=len(issues), sessions=len(plan.get("days") or [])
    )
    return macros, issues, verdict


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Order issues most severe first, then by which check found them.

    Args:
        issues: Issues to order.

    Returns:
        A new sorted list.
    """
    return sorted(
        issues,
        key=lambda issue: (_SEVERITY_ORDER.get(issue["severity"], 3), issue["source"]),
    )


def _enabled_scopes(scope: list[VerifyScope] | None) -> tuple[VerifyScope, ...]:
    """Resolve a requested scope to the checks that will actually run.

    Args:
        scope: What the caller asked for. Unknown entries are ignored rather
            than raising — a classifier that invents a scope must not fail the
            turn.

    Returns:
        The enabled scopes. Never empty: an unrecognised scope assesses
        everything, because scoring nothing and reporting a pass is the one
        outcome that must not be reachable.
    """
    enabled = tuple(item for item in scope or [] if item in _ALL_SCOPES)
    if not enabled:
        return _ALL_SCOPES

    logger.info("verification_scope_selected", scope=list(enabled))
    return enabled


def _verdict_for(issues: list[Issue]) -> Verdict:
    """Reduce an issue list to a single verdict.

    Args:
        issues: Every issue found this run.

    Returns:
        ``"fail"`` if anything blocks, ``"warn"`` if anything warns, else
        ``"pass"``.
    """
    severities = {issue["severity"] for issue in issues}
    if "block" in severities:
        return "fail"
    if "warn" in severities:
        return "warn"
    return "pass"


def _log(source: VerifyScope, issues: list[Issue]) -> None:
    """Emit one log line per check with its blocking count.

    Args:
        source: Which check ran.
        issues: What it found.
    """
    logger.info(
        "verification_check_completed",
        check=source,
        issue_count=len(issues),
        blocking=sum(1 for issue in issues if issue["severity"] == "block"),
    )


__all__ = [
    "run_checks",
    "score",
    "sessions_for",
    "sort_issues",
    "verify_injury",
    "verify_macro",
    "verify_volume",
]
