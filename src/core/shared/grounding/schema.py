"""Shared grounded-claim contract for research → planner → renderer → verifier."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GroundedClaim(BaseModel):
    """A factual claim tied to a concrete source URL (and optional finding id)."""

    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    finding_id: str | None = None
