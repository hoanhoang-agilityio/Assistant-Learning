"""Nodes of the verification agent.

The three verify nodes run concurrently and all write ``issues``, which is why
that field carries an ``add`` reducer. They write nothing else — concurrent
plain writes to a shared field are a lost-update bug that only shows under load.
"""

from langchain_core.runnables import RunnableConfig

from app.core.langgraph.agents.verification.checks import check_injury, check_macro, check_volume
from app.core.langgraph.agents.verification.state import VerifyState
from app.core.logging import logger
from app.schemas.graph import Issue, Verdict
from app.services.rubrics import contraindications, macro_rules, volume_landmarks

# A single blocking finding fails the plan. Warnings never do: they are judgment
# calls the user is entitled to overrule, and treating them as failures would
# spend the repair budget on things that were never wrong.
_SEVERITY_ORDER = {"block": 0, "warn": 1, "info": 2}


async def verify_macro(state: VerifyState, config: RunnableConfig) -> dict:
    """Assess nutrition targets against the macro rubric.

    Reads ``computed_macros`` and ``profile``. Writes ``issues``.

    Args:
        state: Current verify state.
        config: Runnable config. Unused — the check performs no I/O.

    Returns:
        The issues this check produced, merged by the ``add`` reducer.
    """
    issues = check_macro(
        state.get("computed_macros") or {}, state.get("profile") or {}, macro_rules()
    )
    _log("macro", issues)
    return {"issues": issues}


async def verify_volume(state: VerifyState, config: RunnableConfig) -> dict:
    """Assess weekly volume, frequency and session length.

    Reads ``plan`` and ``catalog``. Writes ``issues``.

    Args:
        state: Current verify state.
        config: Runnable config. Unused — the check performs no I/O.

    Returns:
        The issues this check produced, merged by the ``add`` reducer.
    """
    issues = check_volume(state.get("plan") or {}, state.get("catalog") or {}, volume_landmarks())
    _log("volume", issues)
    return {"issues": issues}


async def verify_injury(state: VerifyState, config: RunnableConfig) -> dict:
    """Assess the plan against the user's declared injuries.

    Reads ``plan``, ``profile`` and ``catalog``. Writes ``issues``.

    Args:
        state: Current verify state.
        config: Runnable config. Unused — the check performs no I/O.

    Returns:
        The issues this check produced, merged by the ``add`` reducer.
    """
    issues = check_injury(
        state.get("plan") or {},
        state.get("profile") or {},
        state.get("catalog") or {},
        contraindications(),
    )
    _log("injury", issues)
    return {"issues": issues}


async def merge_issues(state: VerifyState, config: RunnableConfig) -> dict:
    """Set the verdict from the issues every branch collected.

    Reads ``issues``. Writes ``verdict`` — and deliberately not ``issues``.

    The join point of the fan-out: it runs once, after every enabled verifier has
    completed, because LangGraph waits for all inbound edges.

    ``issues`` is not written back. Its reducer is ``add``, so returning a
    reordered copy would concatenate onto what the branches already merged and
    every issue would appear twice. Ordering is presentation, applied by the
    consumer through ``sort_issues``.

    Args:
        state: Current verify state with issues from every branch.
        config: Runnable config. Unused — this node performs no I/O.

    Returns:
        The verdict.
    """
    issues = state.get("issues") or []
    verdict = _verdict_for(issues)
    logger.info(
        "verification_verdict",
        verdict=verdict,
        issue_count=len(issues),
        blocking=sum(1 for issue in issues if issue["severity"] == "block"),
    )
    return {"verdict": verdict}


def sort_issues(issues: list[Issue]) -> list[Issue]:
    """Order issues most severe first, then by which verifier found them.

    Args:
        issues: Issues to order.

    Returns:
        A new sorted list.
    """
    return sorted(
        issues,
        key=lambda issue: (_SEVERITY_ORDER.get(issue["severity"], 3), issue["source"]),
    )


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


def _log(source: str, issues: list[Issue]) -> None:
    """Emit one log line per verifier with its blocking count.

    Args:
        source: Which verifier ran.
        issues: What it found.
    """
    logger.info(
        "verification_check_completed",
        check=source,
        issue_count=len(issues),
        blocking=sum(1 for issue in issues if issue["severity"] == "block"),
    )
