from __future__ import annotations

from typing import Any

from core.mcp.tavily_client import TavilyMCPClient

_MOCK_EVIDENCE_BODY = (
    "Evidence-based fitness programming for fat loss and muscle retention. "
    "Resistance training with hypertrophy and strength work supports macro targets, "
    "caloric deficit planning, protein intake, recovery, and weekly training volume. "
    "Training plan structure includes upper lower splits, compound lifts, and accessory work."
)


def build_mock_tavily_client() -> TavilyMCPClient:
    """Return a Tavily client with deterministic research responses for local dev."""

    def search(query: str, include_domains: list[str] | None = None) -> dict[str, Any]:
        return {
            "results": [
                {
                    "title": f"Evidence for {query[:80]}",
                    "url": "https://example.edu/fitness-training-hypertrophy",
                    "content": _MOCK_EVIDENCE_BODY,
                    "score": 0.95,
                },
                {
                    "title": "Strength and macro guidance",
                    "url": "https://example.org/resistance-training-nutrition",
                    "content": (
                        "Training plan guidance for strength programming, protein targets, "
                        "calories, and recovery during fat loss."
                    ),
                    "score": 0.88,
                },
            ]
        }

    def extract(urls: list[str]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "url": url,
                    "raw_content": f"{_MOCK_EVIDENCE_BODY} Source: {url}",
                }
                for url in urls
            ]
        }

    return TavilyMCPClient(search=search, extract=extract)
