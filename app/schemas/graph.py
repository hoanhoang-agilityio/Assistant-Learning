"""The value types that cross agent boundaries.

State itself lives with the agent that owns it — ``SupervisorState`` in
``core/langgraph/supervisor/``, ``PlanningState`` and ``ReviewState`` in their
packages. What is here is the vocabulary they share: what a finding is, what a
verdict is, and the envelopes a tool may return. Verification has no state of
its own to place: it is plain functions over their arguments
(``core/langgraph/scoring.py``).

Two design constraints are enforced here rather than left to convention:

* **State stays small.** LangGraph re-serialises the whole state after *every*
  node, so full plan snapshots live in Postgres or in the draft store, and state
  carries only ids.
* **A handle is not content.** ``DraftEnvelope`` carries a ``draft_id`` and a
  rendering; ``ReviewEnvelope`` deliberately carries neither an id nor anything
  a save would accept. The difference between "a plan the user will follow" and
  "a plan the user asked about" is that one field.
"""

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

Intent = Literal[
    "build_plan",
    "change_plan",
    "check",
    "revert",
    "general_qa",
    "off_topic",
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


class GoalConflict(TypedDict):
    """A goal this turn implies, set against the one already stored.

    Both sides are carried because the question put to the user names them
    both — "you had muscle gain, this reads like fat loss" — and neither is
    recoverable later: ``stored`` is about to be read by ``calc_macros``, and
    ``implied`` is never written to the profile at all.
    """

    stored: str
    implied: str


class VersionRef(TypedDict):
    """Pointer to a plan snapshot stored in the ``plan_versions`` table."""

    version_id: str
    label: str
    created_at: str


class DraftEnvelope(TypedDict):
    """What a plan-producing tool returns to the supervisor.

    The ``draft_id`` is a *handle*, and that is the whole mechanic
    The plan JSON itself never travels through the
    supervisor's context, so there is no moment where a model retypes a set
    count on its way to being saved. ``save_plan`` accepts the handle and reads
    the content back out of the draft store.

    ``plan_rendered`` is text to describe the plan from, not material to
    reconstruct it out of. ``diff`` is ``None`` for a build — there is nothing to
    compare against — and is what the confirm question shows for everything else.
    """

    status: Literal["draft"]
    draft_id: str
    plan_rendered: str
    macros: dict
    issues: list[Issue]
    verdict: Verdict
    diff: dict | None


class ReviewEnvelope(TypedDict):
    """What ``score_plan`` returns for a plan the user pasted in.

    Deliberately carries **no** ``draft_id``. That absence is the enforcement:
    a review produces nothing ``save_plan`` will accept, so the plan someone was
    only curious about cannot become the plan they follow. The two separate
    state fields that used to enforce it are gone; the missing handle replaces
    them.
    """

    status: Literal["review"]
    plan_rendered: str
    macros: dict
    issues: list[Issue]
    verdict: Verdict


class MissingFields(TypedDict):
    """Refusal returned by a tool whose profile precondition is unmet.

    Returned rather than raised: the supervisor's next move is to ask for the
    listed fields, and a refusal it can read is what makes calling the tool
    anyway achieve nothing but a list of what to ask for.
    """

    status: Literal["missing_fields"]
    fields: list[str]


class ToolRefusal(TypedDict):
    """Any other precondition a tool declined on, with the reason to relay."""

    status: Literal["refused"]
    reason: str


class SavedVersion(TypedDict):
    """What ``save_plan`` returns once the snapshot is in ``plan_versions``."""

    status: Literal["saved"]
    version_id: str
    label: str


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
        default=None,
        description=(
            "fat_loss, muscle_gain, recomp or general_health. Only when the user "
            "states their goal outright. Overwrites the stored one."
        ),
    )
    implied_goal: str | None = Field(
        default=None,
        description=(
            "The same vocabulary, but for a goal the user only implies while "
            "saying something else — 'keep muscle while losing fat' asked as a "
            "protein question. Never set this and `goal` together: an outright "
            "statement belongs in `goal`. This one never overwrites the stored "
            "goal; it is what makes the assistant ask instead of assuming."
        ),
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
