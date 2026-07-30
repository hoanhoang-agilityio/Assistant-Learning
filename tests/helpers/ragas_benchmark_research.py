"""RAGAS-benchmark-only research overrides: evidence content that genuinely
entails its own claims, for use with a real (not heuristic) Ragas judge.

Kept separate from tests/helpers/research.py deliberately -- that module's
default_research_agent_result() ships one generic evidence sentence
("Evidence-based hypertrophy and fat loss programming guidance.") which is
fine for the heuristic token-overlap scorer and every other test that only
checks evidence is present, but fails real NLI-based entailment checking
outright: a 2026-07-29 baseline run scored all 3 clean golden cases at 0.0
real faithfulness, traced to this exact evidence/claim mismatch, not a real
faithfulness failure.

Three content bundles (not a per-case-unique system -- that would be more
mock-building than a sanity-check golden set warrants): BUNDLE_FAT_LOSS,
BUNDLE_MUSCLE_GAIN, BUNDLE_CUTTING_NEAT each pair 2-3 claims with evidence
that actually supports them, so golden cases assigned to different bundles
produce genuinely different grounded_claims.md content, not byte-identical
text differing only in macro numbers.
"""

from typing import Any

from core.shared.grounding.schema import GroundedClaim
from core.subgraphs.research.schema import ResearchAgentResult, ResearchFindings


def _build_result(
    *,
    consensus: str,
    claims: list[tuple[str, str]],
    evidence: list[dict[str, Any]],
) -> ResearchAgentResult:
    key_findings = [
        GroundedClaim(claim=text, source_url=url, finding_id=f"kf_{index}")
        for index, (text, url) in enumerate(claims)
    ]
    urls = sorted({url for _, url in claims})
    structured = ResearchFindings(
        consensus=consensus,
        key_findings=key_findings,
        recommended_sources=urls,
    )
    sources = [
        {
            "source_id": f"q:{index}",
            "title": url.rsplit("/", 1)[-1].replace("-", " ").title(),
            "url": url,
            "snippet": consensus[:80],
            "score": 0.9,
            "provider": "tavily",
            "research_query": "benchmark",
            "verified": True,
            "authority_tier": "whitelist",
            "authority_score": 1.0,
            "composite_score": 0.9,
            "rank": index + 1,
        }
        for index, url in enumerate(urls)
    ]
    summary = f"{consensus}\n\nKey findings:\n" + "\n".join(f"- {t} ({u})" for t, u in claims)
    return ResearchAgentResult(
        sources=sources,
        evidence=evidence,
        structured_findings=structured,
        evidence_summary=summary,
        agent_iterations=1,
    )


BUNDLE_FAT_LOSS: ResearchAgentResult = _build_result(
    consensus=(
        "Resistance training combined with a moderate caloric deficit supports fat loss "
        "while preserving lean mass for recreationally active adults."
    ),
    claims=[
        (
            "Progressive resistance training 3-4 days per week supports fat loss outcomes.",
            "https://example.edu/fitness-training-hypertrophy",
        ),
        (
            "Protein intake near 1.6-2.2 g/kg/day aids lean mass retention during cutting.",
            "https://example.org/resistance-training-nutrition",
        ),
        (
            "Training volume should match recovery capacity and activity level.",
            "https://example.edu/fitness-training-hypertrophy",
        ),
    ],
    evidence=[
        {
            "document_id": "doc_0",
            "url": "https://example.edu/fitness-training-hypertrophy",
            "content": (
                "Systematic reviews of resistance training programming recommend "
                "performing structured resistance training sessions 3 to 4 days per "
                "week to support fat loss outcomes in recreationally active adults. "
                "Assigned training volume should be matched to the individual's "
                "recovery capacity and current activity level to avoid overreaching."
            ),
            "provider": "tavily",
        },
        {
            "document_id": "doc_1",
            "url": "https://example.org/resistance-training-nutrition",
            "content": (
                "During a caloric deficit ('cutting') phase, protein intake in the "
                "range of 1.6 to 2.2 grams per kilogram of bodyweight per day is "
                "recommended to help preserve lean muscle mass while losing fat."
            ),
            "provider": "tavily",
        },
    ],
)

BUNDLE_MUSCLE_GAIN: ResearchAgentResult = _build_result(
    consensus=(
        "Compound lift practice combined with a modest caloric surplus and progressive "
        "overload supports lean muscle and strength gain in intermediate lifters."
    ),
    claims=[
        (
            "Compound lifts such as squat, bench press, and deadlift performed 2-3 times "
            "per week each support strength gains in intermediate lifters.",
            "https://example.edu/compound-lift-frequency",
        ),
        (
            "A caloric surplus of 200-300 calories above maintenance supports lean "
            "muscle gain while limiting fat gain.",
            "https://example.org/lean-bulk-surplus",
        ),
        (
            "Progressive overload, adding load or reps over time, is the primary "
            "driver of long-term strength adaptation.",
            "https://example.edu/compound-lift-frequency",
        ),
    ],
    evidence=[
        {
            "document_id": "doc_0",
            "url": "https://example.edu/compound-lift-frequency",
            "content": (
                "Programming research on compound lift frequency recommends training "
                "major compound lifts (squat, bench press, deadlift) 2 to 3 times per "
                "week for intermediate lifters to accumulate sufficient practice and "
                "strength adaptation. Progressive overload -- adding load or "
                "repetitions over time -- is identified as the primary long-term "
                "driver of strength gains."
            ),
            "provider": "tavily",
        },
        {
            "document_id": "doc_1",
            "url": "https://example.org/lean-bulk-surplus",
            "content": (
                "Lean bulking research recommends a modest caloric surplus of 200 to "
                "300 calories above maintenance to support muscle gain while limiting "
                "excess fat gain."
            ),
            "provider": "tavily",
        },
    ],
)

BUNDLE_CUTTING_NEAT: ResearchAgentResult = _build_result(
    consensus=(
        "A moderate caloric deficit combined with resistance training and attention to "
        "daily activity level supports fat loss while preserving strength and lean mass."
    ),
    claims=[
        (
            "A structured resistance training program combined with a moderate "
            "caloric deficit of 15-20% below maintenance supports fat loss while "
            "preserving strength.",
            "https://example.edu/moderate-deficit-fatloss",
        ),
        (
            "Higher step counts and non-exercise activity (NEAT) meaningfully "
            "contribute to total daily energy expenditure during a fat loss phase.",
            "https://example.org/neat-energy-expenditure",
        ),
        (
            "Maintaining protein intake above 1.6 g/kg bodyweight during a deficit "
            "helps preserve lean mass.",
            "https://example.edu/moderate-deficit-fatloss",
        ),
    ],
    evidence=[
        {
            "document_id": "doc_0",
            "url": "https://example.edu/moderate-deficit-fatloss",
            "content": (
                "Research on moderate caloric deficits for fat loss recommends a 15 "
                "to 20 percent reduction below maintenance calories, combined with "
                "structured resistance training, to support fat loss while "
                "preserving strength and lean mass. Protein intake above 1.6 grams "
                "per kilogram of bodyweight during the deficit further helps "
                "preserve lean mass."
            ),
            "provider": "tavily",
        },
        {
            "document_id": "doc_1",
            "url": "https://example.org/neat-energy-expenditure",
            "content": (
                "Research on non-exercise activity thermogenesis (NEAT) shows that "
                "higher daily step counts and general daily movement meaningfully "
                "contribute to total daily energy expenditure, which is relevant "
                "during a fat loss phase."
            ),
            "provider": "tavily",
        },
    ],
)

_BUNDLES_BY_QUERY: dict[str, ResearchAgentResult] = {}


def register_query_bundle(query: str, bundle: ResearchAgentResult) -> None:
    """Map an exact GoldenCase.query string to a content bundle (see the
    module docstring for why bundles, not per-case-unique content)."""
    _BUNDLES_BY_QUERY[query] = bundle


def ragas_benchmark_research_override(*, query: str = "", **_kwargs: Any) -> ResearchAgentResult:
    """Return the bundle registered for this exact query text, defaulting to
    BUNDLE_FAT_LOSS for any query not explicitly mapped (keeps the original 3
    golden cases working without requiring every case to register)."""
    return _BUNDLES_BY_QUERY.get(query) or BUNDLE_FAT_LOSS


register_query_bundle(
    "Build muscle with a hypertrophy training plan and macro targets.", BUNDLE_MUSCLE_GAIN
)
register_query_bundle(
    "Calculate my macros for a cutting phase with gym training.", BUNDLE_CUTTING_NEAT
)
register_query_bundle(
    "Help me recomposition - keep strength while slowly losing a bit of fat, training 4 days a week.",
    BUNDLE_CUTTING_NEAT,
)
register_query_bundle(
    "I'm new to lifting and want to build muscle safely, training 3 days a week.",
    BUNDLE_MUSCLE_GAIN,
)
register_query_bundle(
    "Calculate my macros for a lean bulk phase with gym training, 5 days a week.",
    BUNDLE_MUSCLE_GAIN,
)
register_query_bundle(
    "I want an aggressive-but-safe 6-day training plan to lose weight.", BUNDLE_CUTTING_NEAT
)
register_query_bundle(
    "I'm 55 and want to build muscle and strength safely with a 3-day plan.", BUNDLE_MUSCLE_GAIN
)
