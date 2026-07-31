"""Deterministic relevance-based content compression for evidence excerpts.

Evidence documents come from real fetched pages (Tavily extract) -- boilerplate
or navigation text is often first, so blind first-N-character truncation (the
previous approach in research/utils.py) can cut away the one sentence with the
specific number or finding that would make a claim citable at all. That's the
same tension L1 Phase 4 Stage B ran into: an honest LLM correctly declines to
cite a claim it never actually saw, but the reason it never saw it was
truncation, not a genuine absence of evidence.

This scores sentence-level chunks with two cheap, deterministic signals --
numeric/unit density and word overlap with the query -- and greedily keeps the
highest-scoring chunks (re-assembled in original order) until the character
budget is spent, instead of keeping whatever happened to come first. Same
scoring also ranks whole documents against each other, for callers choosing
which N of more-than-N evidence docs to keep.
"""

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD_PATTERN = re.compile(r"[a-z0-9]+")
_NUMBER_PATTERN = re.compile(r"\d")
_UNIT_HINTS: tuple[str, ...] = (
    "kg",
    "lb",
    "lbs",
    "%",
    "kcal",
    "calorie",
    "gram",
    "g/kg",
    "protein",
    "rep",
    "set",
    "week",
    "1rm",
    "rm",
)
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "is",
        "are",
        "how",
        "what",
        "my",
        "me",
        "this",
        "that",
        "be",
        "as",
        "at",
        "by",
        "from",
        "it",
        "your",
        "you",
        "can",
        "will",
        "should",
    }
)


def query_terms(query: str) -> frozenset[str]:
    """Lowercased, stopword-filtered tokens from a query for relevance scoring."""
    words = _WORD_PATTERN.findall(query.lower())
    return frozenset(word for word in words if len(word) > 2 and word not in _STOPWORDS)


def _split_sentences(text: str) -> list[str]:
    return [chunk.strip() for chunk in _SENTENCE_SPLIT.split(text) if chunk.strip()]


def _score_chunk(chunk: str, terms: frozenset[str]) -> float:
    lowered = chunk.lower()
    score = 0.0
    if _NUMBER_PATTERN.search(chunk):
        score += 2.0
    score += sum(0.5 for hint in _UNIT_HINTS if hint in lowered)
    if terms:
        words = frozenset(_WORD_PATTERN.findall(lowered))
        score += 1.5 * len(words & terms)
    return score


def score_content(content: str, terms: frozenset[str] = frozenset()) -> float:
    """Aggregate relevance score for a whole document -- ranks which evidence
    documents matter most, not just how to truncate a single one."""
    chunks = _split_sentences(content) or ([content] if content else [])
    return sum(_score_chunk(chunk, terms) for chunk in chunks)


def compress_content(content: str, *, max_chars: int, terms: frozenset[str] = frozenset()) -> str:
    """Keep the highest-signal sentences of `content` within `max_chars`.

    Falls back to a blind prefix slice when there's no sentence punctuation to
    split on, or when no chunk fits at all (e.g. one long run-on sentence) --
    the same worst case as the truncation this replaces, never worse.
    """
    if len(content) <= max_chars:
        return content
    chunks = _split_sentences(content)
    if not chunks:
        return content[:max_chars]
    scored_indices = sorted(
        range(len(chunks)), key=lambda index: _score_chunk(chunks[index], terms), reverse=True
    )
    selected: set[int] = set()
    total = 0
    for index in scored_indices:
        chunk_len = len(chunks[index]) + 1
        if total + chunk_len > max_chars:
            continue
        selected.add(index)
        total += chunk_len
    if not selected:
        return content[:max_chars]
    return " ".join(chunks[index] for index in sorted(selected))
