"""Input scanning for the ``llm_guard`` node."""

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.core.configs.config import GuardScanner, settings
from src.utils.logging import logger

if TYPE_CHECKING:
    from llm_guard.input_scanners.base import Scanner

# Shown when a scanner rejects the query but is not in ``BLOCK_REASONS`` — a scanner added
# to the enum without a message here still produces something a user can read.
DEFAULT_BLOCK_REASON = (
    "Sorry, we can't help with this request because it doesn't meet our safety guidelines. "
    "You're welcome to try something else."
)

# Shown when the guard could not run at all. Deliberately vague about the cause: the user
# cannot act on "the toxicity model failed to load", and the detail belongs in the logs.
GUARD_FAILURE_REASON = (
    "This request could not be safety-checked, so it was not processed. "
    "Please try again in a moment."
)

# Keyed by llm-guard's own scanner class names, which is what ``scan_prompt`` reports.
BLOCK_REASONS: dict[str, str] = {
    "BanSubstrings": "This request contains wording that is not allowed.",
    "BanTopics": "This assistant only covers fitness training and nutrition.",
    "InvisibleText": "This request contains hidden characters.",
    "PromptInjection": (
        "This request looks like an attempt to override the assistant's instructions."
    ),
    "Regex": "This request matches a pattern that is not allowed.",
    "Secrets": "This request appears to contain a password, key or other credential.",
    "TokenLimit": "This request is too long. Please shorten it and try again.",
    "Toxicity": "This request contains abusive or harmful language.",
}


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    """The outcome of scanning one user query."""

    is_blocked: bool
    reason: str | None = None
    failed_scanners: tuple[str, ...] = ()
    scores: dict[str, float] = field(default_factory=dict)


_scanners: "list[Scanner] | None" = None
_scanners_lock = threading.Lock()


def build_scanners() -> "list[Scanner]":
    """Construct the configured scanners in cheapest-first order.

    Enabled scanners with nothing to match on — no banned substrings, no patterns — are
    skipped with a warning instead of being constructed empty, so a half-configured
    deployment is visible in the logs rather than silently permissive.

    Returns:
        list[Scanner]: The scanners to hand to ``scan_prompt``.
    """
    # Deferred on purpose — see the module docstring: a top-level import would make every
    # process that touches ``src`` pay for torch and transformers.
    from llm_guard.input_scanners import (  # noqa: PLC0415
        BanSubstrings,
        BanTopics,
        InvisibleText,
        PromptInjection,
        Regex,
        Secrets,
        TokenLimit,
        Toxicity,
    )

    builders: dict[GuardScanner, Callable[[], Scanner | None]] = {
        GuardScanner.INVISIBLE_TEXT: InvisibleText,
        GuardScanner.BAN_SUBSTRINGS: lambda: (
            BanSubstrings(
                substrings=settings.GUARD_BANNED_SUBSTRINGS, match_type="word"
            )
            if settings.GUARD_BANNED_SUBSTRINGS
            else None
        ),
        GuardScanner.REGEX: lambda: (
            Regex(
                patterns=settings.GUARD_BANNED_PATTERNS, is_blocked=True, redact=False
            )
            if settings.GUARD_BANNED_PATTERNS
            else None
        ),
        GuardScanner.SECRETS: Secrets,
        GuardScanner.TOKEN_LIMIT: lambda: TokenLimit(
            limit=settings.GUARD_MAX_INPUT_TOKENS
        ),
        GuardScanner.PROMPT_INJECTION: lambda: PromptInjection(
            threshold=settings.GUARD_PROMPT_INJECTION_THRESHOLD,
            use_onnx=settings.GUARD_USE_ONNX,
        ),
        GuardScanner.TOXICITY: lambda: Toxicity(
            threshold=settings.GUARD_TOXICITY_THRESHOLD,
            use_onnx=settings.GUARD_USE_ONNX,
        ),
        GuardScanner.BAN_TOPICS: lambda: (
            BanTopics(
                topics=settings.GUARD_BANNED_TOPICS,
                threshold=settings.GUARD_BANNED_TOPICS_THRESHOLD,
                use_onnx=settings.GUARD_USE_ONNX,
            )
            if settings.GUARD_BANNED_TOPICS
            else None
        ),
    }
    # Iterating the enum rather than the setting is what pins the execution order: the
    # setting is a set of names and may arrive from the environment in any order.
    enabled = set(settings.GUARD_SCANNERS)
    scanners: list[Scanner] = []
    for name in GuardScanner:
        if name not in enabled:
            continue
        scanner = builders[name]()
        if scanner is None:
            logger.warning(
                "guard_scanner_skipped", scanner=name.value, reason="not_configured"
            )
            continue
        scanners.append(scanner)
    return scanners


def get_scanners() -> "list[Scanner]":
    """Return the process-wide scanner list, building it on first call.

    The lock is not decoration: scans run in worker threads, so two concurrent first
    requests would otherwise each load every model and one full set would be discarded.

    Returns:
        list[Scanner]: The cached scanners.
    """
    global _scanners
    with _scanners_lock:
        if _scanners is None:
            _scanners = build_scanners()
        return _scanners


def reset_guard() -> None:
    """Drop the cached scanners so the next scan rebuilds them from current settings."""
    global _scanners
    with _scanners_lock:
        _scanners = None


def _scan(prompt: str) -> tuple[dict[str, bool], dict[str, float]]:
    """Run the scanners over a prompt. Synchronous and CPU-bound — call it in a thread.

    Args:
        prompt: The raw user query.

    Returns:
        tuple: Validity per scanner, and risk score per scanner.
    """
    from llm_guard import scan_prompt  # noqa: PLC0415  (deferred, as above)

    _, results_valid, results_score = scan_prompt(
        get_scanners(), prompt, fail_fast=settings.GUARD_FAIL_FAST
    )
    # The sanitized prompt is discarded on purpose. Redacting scanners would rewrite the
    # query, and every node after this one is supposed to read what the user actually
    # wrote; a query containing a secret is rejected outright rather than silently masked.
    return results_valid, results_score


async def scan_input(prompt: str) -> GuardVerdict:
    """Scan one user query with the configured input scanners.

    Args:
        prompt: The raw user query for this turn.

    Returns:
        GuardVerdict: The decision, plus per-scanner scores for logging and tracing.
    """
    if not settings.GUARD_ENABLED:
        return GuardVerdict(is_blocked=False)

    try:
        results_valid, results_score = await asyncio.to_thread(_scan, prompt)
    except Exception as e:
        logger.exception("guard_scan_failed", error=str(e))
        return GuardVerdict(is_blocked=True, reason=GUARD_FAILURE_REASON)

    failed = tuple(name for name, is_valid in results_valid.items() if not is_valid)
    if not failed:
        logger.debug("guard_scan_passed", scores=results_score)
        return GuardVerdict(is_blocked=False, scores=results_score)

    logger.warning("guard_scan_blocked", failed_scanners=failed, scores=results_score)
    return GuardVerdict(
        is_blocked=True,
        reason=BLOCK_REASONS.get(failed[0], DEFAULT_BLOCK_REASON),
        failed_scanners=failed,
        scores=results_score,
    )


async def warm_guard() -> None:
    """Build the scanners at startup so no request pays the model-loading cost.

    Never raises. A failed warm-up leaves the scanners to be built on first use, and if
    they fail there too, ``scan_input`` blocks the request rather than letting it through.
    """
    if not settings.GUARD_ENABLED:
        logger.info("guard_disabled")
        return

    started = time.perf_counter()
    try:
        scanners = await asyncio.to_thread(get_scanners)
    except Exception as e:
        logger.exception("guard_warmup_failed", error=str(e))
        return

    logger.info(
        "guard_warmed",
        scanners=[type(scanner).__name__ for scanner in scanners],
        elapsed_seconds=round(time.perf_counter() - started, 2),
    )


__all__ = [
    "BLOCK_REASONS",
    "DEFAULT_BLOCK_REASON",
    "GUARD_FAILURE_REASON",
    "GuardVerdict",
    "build_scanners",
    "get_scanners",
    "reset_guard",
    "scan_input",
    "warm_guard",
]
