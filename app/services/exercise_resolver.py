"""Map free-text exercise names onto catalog ids.

Tiered, and every tier reports a confidence:

1. exact match on the normalised name or a known alias → ``1.0``
2. token-set overlap ("bench press barbell" ≈ "Barbell Bench Press") → ``0.8``
3. character-similarity fallback → the similarity score itself

**Returning ``None`` is the correct behaviour, not a failure.** Mapping "leg
press" onto "leg extension" does not produce a slightly-wrong review; it
produces a confident review of a plan the user is not doing. The injury check
would clear a movement they never perform and miss the one they do.

Implementation note: tiers 2 and 3 run in process over the catalog rather than
in Postgres. The design names ``pg_trgm`` and pgvector, and both are the right
answer at scale — but the catalog is ~100 rows, neither extension is installed
on this database, and the *contract* is what the calling node depends on:
``(exercise_id, confidence, candidates)``. Swapping the backend later changes
nothing above this module.
"""

import re
from difflib import SequenceMatcher
from typing import Any, TypedDict

from app.core.logging import logger

# Below this, the caller must ask the user rather than accept the match.
CONFIDENCE_THRESHOLD = 0.85

_EXACT_CONFIDENCE = 1.0
_TOKEN_CONFIDENCE = 0.8
_MAX_CANDIDATES = 3

# Words that carry no identifying information and only dilute token overlap.
_NOISE_TOKENS = frozenset({"the", "a", "an", "of", "with", "and", "on", "in", "for"})

# Common shorthand users type. Expanded before matching so "db bench" and
# "dumbbell bench press" resolve the same way.
_SYNONYMS: dict[str, str] = {
    "db": "dumbbell",
    "bb": "barbell",
    "kb": "kettlebell",
    "ohp": "overhead press",
    "rdl": "romanian deadlift",
    "bw": "bodyweight",
    "sldl": "romanian deadlift",
    "pullup": "pull up",
    "chinup": "chin up",
    "pushup": "push up",
    "situp": "sit up",
    "lat pulldown": "lat pulldown",
    "leg ext": "leg extension",
    "ez": "ez bar",
}


class Resolution(TypedDict):
    """Outcome of resolving one free-text exercise name."""

    exercise_id: str | None
    confidence: float
    candidates: list[dict[str, str]]


def normalise(text: str) -> str:
    """Reduce a name to comparable form.

    Args:
        text: Raw user text.

    Returns:
        Lowercase, punctuation-free, with shorthand expanded.
    """
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = [_SYNONYMS.get(word, word) for word in cleaned.split()]
    return " ".join(" ".join(words).split())


def _tokens(text: str) -> set[str]:
    """Split a normalised name into meaningful tokens.

    Args:
        text: Normalised text.

    Returns:
        Tokens with noise words removed.
    """
    return {word for word in text.split() if word not in _NOISE_TOKENS}


def resolve_exercise(raw_text: str, catalog: dict[str, dict[str, Any]]) -> Resolution:
    """Resolve a free-text exercise name against the catalog.

    Args:
        raw_text: What the user wrote, e.g. ``"incline db press 3x10"``.
        catalog: Exercise metadata keyed by id.

    Returns:
        A ``Resolution``. ``exercise_id`` is ``None`` whenever confidence falls
        below ``CONFIDENCE_THRESHOLD``; ``candidates`` then carries the closest
        matches so the caller can ask the user to choose.
    """
    query = normalise(raw_text)
    if not query or not catalog:
        return Resolution(exercise_id=None, confidence=0.0, candidates=[])

    names = {
        exercise_id: normalise(entry.get("name", exercise_id))
        for exercise_id, entry in catalog.items()
    }

    # Tier 1 — exact, on the display name or the id itself.
    for exercise_id, name in names.items():
        if query == name or query == normalise(exercise_id):
            return Resolution(exercise_id=exercise_id, confidence=_EXACT_CONFIDENCE, candidates=[])

    # Tier 2 — every meaningful token of the query appears in the name.
    query_tokens = _tokens(query)
    subset_matches = [
        exercise_id
        for exercise_id, name in names.items()
        if query_tokens and query_tokens <= _tokens(name)
    ]
    if len(subset_matches) == 1:
        return Resolution(
            exercise_id=subset_matches[0], confidence=_TOKEN_CONFIDENCE, candidates=[]
        )

    # Tier 3 — character similarity, and it must clear the threshold alone.
    scored = sorted(
        (
            (SequenceMatcher(None, query, name).ratio(), exercise_id)
            for exercise_id, name in names.items()
        ),
        reverse=True,
    )
    best_score, best_id = scored[0]

    if best_score >= CONFIDENCE_THRESHOLD and not subset_matches:
        return Resolution(exercise_id=best_id, confidence=round(best_score, 2), candidates=[])

    # Not confident. Return what it might have been so the caller can ask.
    pool = subset_matches or [exercise_id for _score, exercise_id in scored[:_MAX_CANDIDATES]]
    logger.info(
        "exercise_unresolved",
        raw_text=raw_text[:60],
        best_score=round(best_score, 2),
        candidate_count=len(pool),
    )
    return Resolution(
        exercise_id=None,
        confidence=round(best_score, 2),
        candidates=[
            {"exercise_id": exercise_id, "name": catalog[exercise_id].get("name", exercise_id)}
            for exercise_id in pool[:_MAX_CANDIDATES]
        ],
    )


__all__ = ["CONFIDENCE_THRESHOLD", "Resolution", "normalise", "resolve_exercise"]
