"""Deterministic source verification with configurable authority whitelist."""

from typing import Any
from urllib.parse import urlparse

from core.config.settings import get_settings

DEFAULT_TRUSTED_DOMAINS: tuple[str, ...] = (
    "pubmed.ncbi.nlm.nih.gov",
    "nih.gov",
    "who.int",
    "cdc.gov",
    "acsm.org",
    "jissn.biomedcentral.com",
    "nsca.com",
)

GOVERNMENT_EDU_SUFFIXES: tuple[str, ...] = (".edu", ".gov")

FITNESS_KEYWORDS: tuple[str, ...] = (
    "fitness",
    "training",
    "exercise",
    "hypertrophy",
    "strength",
    "macro",
    "nutrition",
    "workout",
)

AuthorityTier = str  # whitelist | government_edu | fitness_keyword | unverified


def resolve_trusted_domains() -> tuple[str, ...]:
    """Return trusted domain hostnames from settings or built-in defaults."""
    settings = get_settings()
    raw = (settings.research_trusted_domains or "").strip()
    if not raw:
        return DEFAULT_TRUSTED_DOMAINS
    domains = tuple(domain.strip().lower() for domain in raw.split(",") if domain.strip())
    return domains or DEFAULT_TRUSTED_DOMAINS


def has_explicit_trusted_domains() -> bool:
    """True only when research_trusted_domains was deliberately configured --
    distinguishes that from resolve_trusted_domains()'s implicit
    DEFAULT_TRUSTED_DOMAINS fallback. Used to decide whether to pass
    include_domains to Tavily's search call itself (2026-07-30): hard-scoping
    every search to the built-in default list would cut real recall for
    callers who never opted into narrow scoping, so Tavily-side restriction
    only applies when an operator explicitly asked for it."""
    return bool((get_settings().research_trusted_domains or "").strip())


def _hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _matches_whitelist(hostname: str, trusted_domains: tuple[str, ...]) -> bool:
    return any(domain in hostname for domain in trusted_domains)


def _matches_government_edu(hostname: str) -> bool:
    return any(hostname.endswith(suffix) for suffix in GOVERNMENT_EDU_SUFFIXES)


def _is_fitness_relevant(source: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            str(source.get("title", "")),
            str(source.get("snippet", "")),
            str(source.get("url", "")),
        ]
    ).lower()
    return any(keyword in haystack for keyword in FITNESS_KEYWORDS)


def compute_authority_score(hostname: str, trusted_domains: tuple[str, ...]) -> float:
    """Return authority score in [0, 1] for hybrid ranking."""
    if _matches_whitelist(hostname, trusted_domains):
        return 1.0
    if _matches_government_edu(hostname):
        return 0.6
    return 0.2


def classify_authority_tier(
    url: str,
    source: dict[str, Any],
    trusted_domains: tuple[str, ...] | None = None,
) -> AuthorityTier:
    """Classify source authority tier."""
    domains = trusted_domains or resolve_trusted_domains()
    hostname = _hostname(url)
    if _matches_whitelist(hostname, domains):
        return "whitelist"
    if _matches_government_edu(hostname):
        return "government_edu"
    if _is_fitness_relevant(source):
        return "fitness_keyword"
    return "unverified"


def verify_source(
    source: dict[str, Any],
    trusted_domains: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Annotate a source with verification metadata.

    `topically_relevant` (2026-07-30) is a new, always-computed signal --
    domain authority (a `.edu`/`.gov`/whitelisted host) says nothing about
    whether the actual content is about fitness at all (found via a real run
    whose evidence included an unrelated materials-science paper, likely
    passed on domain trust alone). It deliberately does NOT gate `verified`
    here, though: `_is_fitness_relevant`'s keyword list is too blunt to trust
    as a hard gate on `verified` -- a genuinely relevant source (e.g. a real
    PubMed systematic review) can easily have title/snippet text that
    contains none of those 8 words, and `verified` feeds
    `has_sufficient_research_coverage`'s skip-further-searching shortcut,
    where that kind of false negative just burns extra search/eval calls on
    already-good sources for no benefit. `topically_relevant` instead feeds
    ranking.py's composite score as a *demotion*, not a hard admission gate --
    the same false negative there just means a good source ranks slightly
    lower, which self-corrects when better sources exist and costs nothing
    when they don't. `authority_tier` remains a pure domain-trust
    classification, unaffected either way.
    """
    domains = trusted_domains or resolve_trusted_domains()
    url = str(source.get("url", ""))
    hostname = _hostname(url)
    tier = classify_authority_tier(url, source, domains)
    relevant = _is_fitness_relevant(source)
    verified = tier in {"whitelist", "government_edu", "fitness_keyword"}
    authority_score = compute_authority_score(hostname, domains)
    return {
        **source,
        "verified": verified,
        "authority_tier": tier,
        "authority_score": authority_score,
        "topically_relevant": relevant,
    }


def verify_sources_data(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify all sources and return annotated list."""
    domains = resolve_trusted_domains()
    verified_sources = [verify_source(source, domains) for source in sources]
    return {"sources": verified_sources}
