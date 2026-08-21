"""Map free-text exercise names onto catalog ids.

Tiered, and every tier reports a confidence:

1. exact match on the normalised name or a known alias → ``1.0``
2. token-set overlap ("bench press barbell" ≈ "Barbell Bench Press") → ``0.8``
3. one candidate once style qualifiers are discounted → ``0.8``
4. several candidates that no check could tell apart → ``0.75``
5. character-similarity fallback → the similarity score itself

**Returning ``None`` is the correct behaviour, not a failure.** Mapping "leg
press" onto "leg extension" does not produce a slightly-wrong review; it
produces a confident review of a plan the user is not doing. The injury check
would clear a movement they never perform and miss the one they do.

Tiers 3 and 4 exist because that principle, applied to *this* catalog, refused
the most ordinary names a user can write. There is no "Bench Press" row, only
"Barbell Bench Press", "Incline Bench Press (Wide Grip)", "Decline Bench Press
(Neutral Grip)" and "Dumbbell Bench Press (Machine)" — so a plain "Bench Press"
matched four rows, none uniquely, and was reported as unidentified. Five of the
twelve lines in an ordinary three-day plan came back that way.

Neither tier weakens the principle, because neither one guesses:

* **Tier 3** discounts tokens that are *style* qualifiers — grip, tempo, machine
  — and keeps content words, which name different exercises. "Leg Press" then
  matches "Leg Press (Neutral Grip)" and not "Leg Press Calf Raise". It only
  fires when exactly one candidate survives, and only for a query specific
  enough to have two meaningful tokens: a bare "press" stays a question.
* **Tier 4** resolves several candidates only after proving the choice cannot
  change the answer: it compares the four fields the checks actually read —
  movement pattern, muscle contribution, joint actions, loaded positions — and
  gives up unless every candidate agrees on all of them. The variants it stands
  down on are returned in ``equivalent`` so the caller can say which one it
  assessed rather than quietly picking.

The distinction that matters is between a choice the user would notice and a
choice no check can see. "Leg press" for "leg extension" is the first. One
bench-press variant for another, when both credit the same muscles through the
same joint actions, is the second.

Implementation note: the fuzzy tiers run in process over the catalog rather than
in Postgres. The design names ``pg_trgm`` and pgvector, and both are the right
answer at scale — but the catalog is ~100 rows, neither extension is installed
on this database, and the *contract* is what the calling node depends on:
``(exercise_id, confidence, candidates, equivalent)``. Swapping the backend
later changes nothing above this module.
"""

import re
from difflib import SequenceMatcher
from typing import Any, TypedDict

from app.core.logging import logger

# Gates tier 5 only. The tiers above it resolve on structure rather than on
# string distance, and report a confidence that describes *how* the match was
# made — several of them sit below this number by design.
CONFIDENCE_THRESHOLD = 0.85

_EXACT_CONFIDENCE = 1.0
_TOKEN_CONFIDENCE = 0.8
_EQUIVALENT_CONFIDENCE = 0.75
_MAX_CANDIDATES = 3

# A query this short is not specific enough to discount anything against: "press"
# is a subset of half the pushing catalog, and every one of them is a different
# exercise. Below this it goes back to the user.
_MIN_TOKENS_FOR_VARIANTS = 2

# Tokens that qualify *how* an exercise is done rather than *which* exercise it
# is. Read off the parenthetical suffixes the catalog actually uses, minus the
# equipment words — "barbell", "dumbbell" and "bodyweight" change what the user
# did, and a plan that says "Squat" must not be assessed as "Bodyweight Squat".
_STYLE_TOKENS = frozenset({"grip", "neutral", "wide", "close", "tempo", "machine", "assisted"})

# What the checks read off a catalog row. Two rows agreeing on all four produce
# the same review, so choosing between them is not a choice the user can see.
# `equipment` and `skill_level` are absent deliberately: they gate what may be
# *planned* for someone, not how a plan they already follow is assessed.
_ASSESSED_FIELDS = ("movement_pattern", "contribution", "joint_actions", "loaded_positions")

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
    equivalent: list[dict[str, str]]


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
        A ``Resolution``. ``exercise_id`` is ``None`` when no tier could settle
        the name; ``candidates`` then carries the closest matches so the caller
        can ask the user to choose. When a tier resolved among several rows the
        checks cannot tell apart, ``equivalent`` names the ones it stood down on.
    """
    query = normalise(raw_text)
    if not query or not catalog:
        return Resolution(exercise_id=None, confidence=0.0, candidates=[], equivalent=[])

    names = {
        exercise_id: normalise(entry.get("name", exercise_id))
        for exercise_id, entry in catalog.items()
    }

    # Tier 1 — exact, on the display name or the id itself.
    for exercise_id, name in names.items():
        if query == name or query == normalise(exercise_id):
            return Resolution(
                exercise_id=exercise_id,
                confidence=_EXACT_CONFIDENCE,
                candidates=[],
                equivalent=[],
            )

    # Tier 2 — every meaningful token of the query appears in exactly one name.
    query_tokens = _tokens(query)
    subset_matches = [
        exercise_id
        for exercise_id, name in names.items()
        if query_tokens and query_tokens <= _tokens(name)
    ]
    if len(subset_matches) == 1:
        return Resolution(
            exercise_id=subset_matches[0],
            confidence=_TOKEN_CONFIDENCE,
            candidates=[],
            equivalent=[],
        )

    # Tiers 3 and 4 — a generic name against a catalog of qualified variants.
    if len(subset_matches) > 1:
        settled = _settle_variants(query_tokens, subset_matches, names, catalog)
        if settled is not None:
            return settled

    # Tier 5 — character similarity, and it must clear the threshold alone.
    scored = sorted(
        (
            (SequenceMatcher(None, query, name).ratio(), exercise_id)
            for exercise_id, name in names.items()
        ),
        reverse=True,
    )
    best_score, best_id = scored[0]

    if best_score >= CONFIDENCE_THRESHOLD and not subset_matches:
        return Resolution(
            exercise_id=best_id, confidence=round(best_score, 2), candidates=[], equivalent=[]
        )

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
        candidates=[_named(exercise_id, catalog) for exercise_id in pool[:_MAX_CANDIDATES]],
        equivalent=[],
    )


def _settle_variants(
    query_tokens: set[str],
    matches: list[str],
    names: dict[str, str],
    catalog: dict[str, dict[str, Any]],
) -> Resolution | None:
    """Settle a generic name that matched several qualified rows, or decline.

    Two ways out, in order. Discount the tokens that only say *how* an exercise
    is done and see whether one row is left — that separates "Leg Press" from
    "Leg Press Calf Raise", which is a different movement wearing a longer name.
    Failing that, prove the remaining rows are indistinguishable to every check
    that will run, in which case picking between them cannot change the review.

    Args:
        query_tokens: Meaningful tokens of what the user wrote.
        matches: Ids whose names contain all of them.
        names: Normalised catalog names, keyed by id.
        catalog: Exercise metadata keyed by id.

    Returns:
        A resolution, or ``None`` to leave the name for the user to settle.
    """
    if len(query_tokens) < _MIN_TOKENS_FOR_VARIANTS:
        return None

    # Rows whose only extra words qualify the style. Everything else names a
    # different exercise: "calf raise" added to "leg press" is not a qualifier.
    pool = [
        exercise_id
        for exercise_id in matches
        if (_tokens(names[exercise_id]) - query_tokens) <= _STYLE_TOKENS
    ] or matches

    if len(pool) > 1 and len({_assessed_key(catalog[i]) for i in pool}) != 1:
        # They differ where it counts. Asking is the only honest move.
        return None

    # The closest name wins, and ties break on the id so the same plan reviewed
    # twice reads the same way.
    chosen = min(pool, key=lambda i: (len(_tokens(names[i]) - query_tokens), i))
    equivalent = [_named(i, catalog) for i in sorted(pool) if i != chosen]
    logger.info(
        "exercise_variant_settled",
        exercise_id=chosen,
        matched=len(matches),
        equivalent_count=len(equivalent),
    )
    return Resolution(
        exercise_id=chosen,
        confidence=_TOKEN_CONFIDENCE if not equivalent else _EQUIVALENT_CONFIDENCE,
        candidates=[],
        equivalent=equivalent,
    )


def _assessed_key(entry: dict[str, Any]) -> str:
    """Reduce a catalog row to what the checks will read off it.

    Args:
        entry: One catalog row.

    Returns:
        A comparable key. Two rows sharing it produce the same assessment.
    """
    return repr([entry.get(field) for field in _ASSESSED_FIELDS])


def _named(exercise_id: str, catalog: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Pair an id with its display name, for a caller that has to name it.

    Args:
        exercise_id: The id.
        catalog: Exercise metadata keyed by id.

    Returns:
        The id and its name.
    """
    return {"exercise_id": exercise_id, "name": catalog[exercise_id].get("name", exercise_id)}


__all__ = ["CONFIDENCE_THRESHOLD", "Resolution", "normalise", "resolve_exercise"]
