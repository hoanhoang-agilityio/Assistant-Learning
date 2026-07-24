from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict

from core.agents.intent_judge import UserIntent, UserIntentJudgement
from core.agents.state import AffectedDomain

WorkflowName = Literal[
    "GenerateWorkflow",
    "EditWorkflow",
    "EditWithReplanWorkflow",
    "VerifyExternalWorkflow",
]
FitnessMode = Literal["generate", "edit", "evaluate"]
VerificationStrategy = Literal["FULL", "EXTERNAL_PLAN", "EDIT_REVIEW"]

_PROFILE_REQUIRING_DOMAINS: frozenset[AffectedDomain] = frozenset(
    {"planning", "research", "fitness"}
)


class RunExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_intent: UserIntent
    workflow: WorkflowName
    ordered_domains: list[AffectedDomain]
    fitness_mode: FitnessMode
    verification_strategy: VerificationStrategy

    @property
    def entry_domain(self) -> AffectedDomain:
        """The first domain in `ordered_domains` -- never stored, always derived."""
        return self.ordered_domains[0]

    @property
    def requires_profile(self) -> bool:
        return any(domain in _PROFILE_REQUIRING_DOMAINS for domain in self.ordered_domains)


class WorkflowTemplate(NamedTuple):
    ordered_domains: list[AffectedDomain]
    fitness_mode: FitnessMode
    verification_strategy: VerificationStrategy


WORKFLOW_TEMPLATES: dict[WorkflowName, WorkflowTemplate] = {
    "GenerateWorkflow": WorkflowTemplate(
        ordered_domains=["planning", "research", "fitness", "verify"],
        fitness_mode="generate",
        verification_strategy="FULL",
    ),
    "EditWorkflow": WorkflowTemplate(
        ordered_domains=["fitness", "verify"],
        fitness_mode="edit",
        verification_strategy="EDIT_REVIEW",
    ),
    "EditWithReplanWorkflow": WorkflowTemplate(
        ordered_domains=["planning", "fitness", "verify"],
        fitness_mode="edit",
        verification_strategy="EDIT_REVIEW",
    ),
    "VerifyExternalWorkflow": WorkflowTemplate(
        ordered_domains=["fitness", "verify"],
        fitness_mode="evaluate",
        verification_strategy="EXTERNAL_PLAN",
    ),
}


def resolve_workflow(judgement: UserIntentJudgement) -> RunExecutionPlan:
    """Deterministically map a `UserIntentJudgement` to a `RunExecutionPlan`.

    Phase 2: built and unit-tested in isolation; not called from `supervisor_node` yet
    (Phase 3). Reads only `judgement` -- no workflow choice in this phase needs live
    profile/run state (design review F10's timing constraint: `RunExecutionPlan` is built
    before the `user` subgraph has necessarily populated the profile on a brand-new run,
    so this resolver must not depend on it, and doesn't).

    `ordered_domains` is copied out of the template, not passed by reference: `WorkflowTemplate`
    instances are shared, long-lived module state, and `RunExecutionPlan` is frozen but that
    only blocks attribute *reassignment* -- a mutation of the underlying list would silently
    corrupt the template (and every other plan built from it) without this copy.
    """
    workflow: WorkflowName
    if judgement.user_intent == "verify":
        workflow = "VerifyExternalWorkflow"
    elif judgement.user_intent == "edit":
        workflow = (
            "EditWithReplanWorkflow" if judgement.touches_goal_or_constraints else "EditWorkflow"
        )
    else:
        workflow = "GenerateWorkflow"

    template = WORKFLOW_TEMPLATES[workflow]
    return RunExecutionPlan(
        user_intent=judgement.user_intent,
        workflow=workflow,
        ordered_domains=list(template.ordered_domains),
        fitness_mode=template.fitness_mode,
        verification_strategy=template.verification_strategy,
    )
