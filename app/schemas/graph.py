"""Graph state and the value types that cross agent boundaries.

Implements two design constraints are enforced here
rather than by convention:

* **State stays small.** LangGraph re-serialises the whole state after *every*
  node, so full plan snapshots live in Postgres and state carries only
  ``VersionRef`` index entries.
* **Only fan-out fields get reducers.** ``issues`` is written by the three
  verify branches concurrently and therefore needs ``add``. Every other field
  is written by exactly one branch; giving it a reducer would hide a
  lost-update bug rather than prevent one.
"""

from operator import add
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Intent = Literal[
    "build_plan",
    "change_plan",
    "check",
    "revert",
    "general_qa",
]

VerifyScope = Literal["macro", "volume", "injury"]

Verdict = Literal["pass", "warn", "fail"]

Severity = Literal["info", "warn", "block"]


class Issue(TypedDict):
    """One rubric violation found by a verifier.

    ``suggestion`` carries a replacement rather than only naming the fault, so
    ``repair`` has something to act on. ``rubric_ref`` makes a verdict traceable
    back to the rule that produced it.
    """

    source: VerifyScope
    severity: Severity
    location: str
    message: str
    suggestion: dict | None
    rubric_ref: str


class VersionRef(TypedDict):
    """Pointer to a plan snapshot stored in the ``plan_versions`` table."""

    version_id: str
    label: str
    created_at: str


class PlanChanges(BaseModel):
    """What a ``change_plan`` turn is asking to alter.

    A closed set of named fields rather than a free-form dict, for two reasons.

    OpenAI's structured output rejects an open object outright — a bare ``dict``
    generates a schema without ``additionalProperties: false`` and the request
    fails with a 400 before the model is ever called. That is a hard constraint,
    not a preference.

    It also matches what ``patch_plan`` can actually apply
    (``SUPPORTED_CHANGES``). A free dict let the classifier emit a change nobody
    could act on; here an unsupported request simply has nowhere to go, and the
    user is told rather than quietly ignored.
    """

    days: int | None = Field(default=None, description="Requested sessions per week")
    goal: str | None = Field(
        default=None, description="fat_loss, muscle_gain, recomp or general_health"
    )


class IntentDecision(BaseModel):
    """Structured output of the ``classify`` node.

    Never parsed out of free text: the classifier is called with
    ``response_format=IntentDecision`` so an unroutable answer fails validation
    instead of silently picking a branch.
    """

    intent: Intent = Field(description="Which branch of the graph handles this turn")
    scope: list[VerifyScope] = Field(
        default_factory=list,
        description="Verifiers to enable this turn. Empty for read-only intents that skip verify.",
    )
    changes: PlanChanges = Field(
        default_factory=PlanChanges,
        description="What to change, for change_plan only. All null for every other intent.",
    )


class ProfileExtraction(BaseModel):
    """Facts ``extract_profile`` pulled out of the conversation this turn.

    Lives here rather than in an agent package because ``extract_profile`` is a
    root-graph node: loading, extracting and gating the profile is orchestration
    the root owns, not an independently packaged capability.

    Every field is optional: a turn usually states one or two things, and the
    profile is accumulated across turns. ``None`` means "not mentioned", which
    must never overwrite a stored value.
    """

    weight_kg: float | None = Field(default=None, description="Body weight in kilograms")
    height_cm: float | None = Field(default=None, description="Height in centimetres")
    age: int | None = Field(default=None, description="Age in years")
    sex: str | None = Field(default=None, description="male or female")
    activity_level: str | None = Field(
        default=None,
        description="Daily life outside training: sedentary, light, moderate, active, very_active",
    )
    days_per_week: int | None = Field(default=None, description="Training sessions per week")
    level: int | None = Field(default=None, description="Training experience, 1 (new) to 5")
    goal: str | None = Field(
        default=None, description="fat_loss, muscle_gain, recomp or general_health"
    )
    equipment: list[str] | None = Field(
        default=None, description="Equipment tokens the user has access to"
    )
    injuries: list[str] | None = Field(
        default=None,
        description="Injury keys from the contraindication rubric. Empty list means none.",
    )
    preferences: str | None = Field(
        default=None, description="Exercises the user likes or wants to avoid, as free text"
    )
    unmapped_injury: str | None = Field(
        default=None,
        description=(
            "An injury the user described that is NOT one of the recognised keys, "
            "in their own words. Set this instead of guessing a key."
        ),
    )


class RootState(BaseModel):
    """State of the root graph — only what crosses agent boundaries.

    Subgraphs declare their own narrower state and the parent maps in and out
    explicitly, so a verifier cannot see the build transcript even by accident
    (``docs/workflow.md`` §1.3, §7.4).
    """

    messages: Annotated[list, add_messages] = Field(default_factory=list)
    long_term_memory: str = Field(
        default="", description="Memory retrieved once per turn at the root facade"
    )

    intent: Intent | None = Field(default=None, description="Set by classify, read by dispatch")
    scope: list[VerifyScope] = Field(
        default_factory=list, description="Which verifiers run this turn"
    )
    changes: dict = Field(default_factory=dict, description="Delta to apply for change_plan")
    revert_target: str | None = Field(
        default=None, description="version_id resolved from natural language for revert"
    )

    profile: dict = Field(default_factory=dict, description="User profile as loaded and extracted")
    missing_fields: list[str] = Field(
        default_factory=list, description="Required profile fields still unanswered"
    )

    plan: dict | None = Field(default=None, description="Approved plan — the source of truth")
    macros: dict | None = Field(default=None, description="Macros belonging to the approved plan")
    submitted_plan: dict | None = Field(
        default=None,
        description="Plan the user pasted in for review. Never written to `plan`.",
    )
    computed_macros: dict | None = Field(
        default=None, description="Macros recomputed this turn, for comparison against `macros`"
    )
    draft_plan: dict | None = Field(default=None, description="Uncommitted working plan")

    issues: Annotated[list[Issue], add] = Field(
        default_factory=list,
        description="Written concurrently by the three verify branches — reducer is mandatory",
    )
    verdict: Verdict | None = Field(default=None, description="Set by merge_issues")
    repair_count: int = Field(
        default=0, description="Repair attempts this turn. Capped at 2 (§8) — must live in state."
    )

    version_index: list[VersionRef] = Field(
        default_factory=list, description="Index only; snapshots live in Postgres"
    )
    current_version_id: str | None = Field(
        default=None, description="Version the user last approved"
    )
    pending_commit: dict | None = Field(
        default=None, description="Staged diff awaiting the interrupt() confirm gate"
    )

    answer: str = Field(default="", description="Final user-facing text for this turn")
