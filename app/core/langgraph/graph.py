"""Root graph and the public facade the API depends on.

One spine, one branch point. Every turn walks ``classify → load_context →
extract_profile → check_required`` and only then takes a branch, at
``intent_branch``. ``classify`` is the only LLM node that influences control
flow, and it does so by returning a validated decision rather than by choosing
what to call. Subgraphs are invoked explicitly with a mapped-in state rather
than attached as nodes, so state keys are never shared by name and an agent
cannot read a field it was not given.

The API sees only the four facade methods at the bottom. It does not know
subgraphs exist, and adding one must not change that. It also does not assemble
context: the graph loads its own, so a caller that is not this facade is not a
degraded caller.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.configs.config import Environment, settings
from app.core.langgraph.agents import AGENTS
from app.core.langgraph.agents.planning.patch import patch_plan
from app.core.langgraph.agents.planning.repair import repair_plan
from app.core.langgraph.agents.qa import EXHAUSTED_ANSWER, FAILURE_ANSWER
from app.core.langgraph.agents.verification import sort_issues
from app.core.langgraph.diff import build_diff
from app.core.langgraph.profile.nodes import check_required, extract_profile, load_context
from app.core.langgraph.routing.classify import classify
from app.core.langgraph.utils import message_text, to_chat_messages
from app.core.langgraph.versioning import (
    describe_verification_reason,
    render_versions,
    resolve_version_id,
)
from app.core.logging import logger
from app.core.observability import get_langfuse_callbacks
from app.core.prompts import load_compose_answer_prompt, load_system_prompt
from app.schemas.chat import Message
from app.schemas.graph import Intent, Issue, RootState
from app.services.catalog import load_catalog
from app.services.llm.service import llm_service
from app.services.nutrition import calc_macros
from app.services.profile import FIELD_LABELS, profile_hash
from app.services.rubrics import rubric_version
from app.services.templates import get_template
from app.services.versions import get_version, insert_version, version_index

GRAPH_NAME = "root"

_COMPOSER_MODEL = "gpt-5-mini"

# How a stored profile field is named to a model. Separate from `FIELD_LABELS`,
# which phrases the same columns as questions to ask the user — "your height
# (cm)" reads as an interrogation when it appears in a list of things already
# known.
_SEMANTIC_LABELS: dict[str, str] = {
    "weight_kg": "Body weight (kg)",
    "height_cm": "Height (cm)",
    "age": "Age",
    "sex": "Sex",
    "activity_level": "Daily activity outside training",
    "days_per_week": "Training days per week",
    "level": "Training experience (1 new – 5 advanced)",
    "goal": "Goal",
    "equipment": "Equipment available",
    "injuries": "Injuries screened by the rubric",
    "preferences": "Stated preferences",
    "unmapped_injury": "Injury described but not in the rubric",
}

# Repair attempts before the issue list goes to the user instead. Two failures
# usually means genuinely conflicting constraints — six sessions a week with
# only bands, and both knees and shoulders hurting — which is a decision for the
# user, not something an agent resolves by trying again.
_MAX_REPAIRS = 2

# Every intent maps to exactly one node. A missing key is a bug, not a runtime
# branch — adding an Intent literal without a target here fails the mapping test.
#
# This is the graph's only branch point, and `check_required` is the only node
# with an edge into it. Those two facts together are what make the profile gate
# unskippable: there is no path to any branch — not `calc_macro`, not `qa` —
# that does not pass the gate first.
#
# `off_topic` is decided by `classify` rather than by a guardrail node in front
# of it: the classifier already reads the conversation and already pays for a
# model call, so the judgment is free, where a separate node would add a
# round-trip to every turn to catch the rare one.
INTENT_TARGETS: dict[Intent, str] = {
    "build_plan": "planning",
    "change_plan": "patch_plan",
    "check": "ingest_plan",
    "revert": "resolve_version",
    "general_qa": "qa",
    "off_topic": "decline",
}

# Intents that overwrite something the user has already approved, and therefore
# stop for confirmation. `build_plan` is absent on
# purpose: there is nothing to lose yet. `check` and `general_qa` are read-only.
CONFIRM_REQUIRED_INTENTS = frozenset({"change_plan", "revert"})

# Intents that assess or answer without changing anything. They never reach
# `snapshot`, so a review of a pasted plan cannot become the user's own plan
READ_ONLY_INTENTS = frozenset({"check", "general_qa"})

# Every branch that is designed but not yet built lands here. Named so the
# message is one honest sentence rather than an invented plan.
_UNBUILT_BRANCH_ANSWER = (
    "I'm not sure what you'd like me to do with your plan. I can build one, "
    "change the one you have, review a plan you paste in, or go back to an "
    "earlier version."
)

_NO_PLAN_FOUND_ANSWER = (
    "I couldn't find a training plan in that message. Paste the plan — days, "
    "exercises, and sets and reps for each — and I'll review it."
)

_DECLINED_ANSWER = (
    "Left your plan as it was. Nothing has changed. Tell me if you want to try a "
    "different adjustment."
)

_NO_HISTORY_ANSWER = (
    "There's no earlier version to go back to — the plan you have is the only one I've saved."
)

# The topic gate's whole reply. Deliberately a constant and not a model call:
# the one thing this branch must never do is engage with the message it is
# declining, and a model handed that message will find a way to help with it.
_OFF_TOPIC_ANSWER = (
    "That's outside what I do — I only work on training plans and the nutrition "
    "that goes with them. Ask me about your plan, your training, or anything "
    "about lifting and eating for it."
)

# Words that count as approval at the confirm gate, across the languages this
# assistant answers in. Anything not listed is treated as "no" — a confirm gate
# that guesses in favour of proceeding is not a gate.
_AFFIRMATIVE = frozenset(
    {
        "yes",
        "y",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "confirm",
        "confirmed",
        "apply",
        "do it",
        "go ahead",
        "proceed",
        "accept",
        "approve",
        "true",
    }
)


class LangGraphAgent:
    """Owns the compiled root graph, the subgraphs and the checkpointer pool."""

    def __init__(self) -> None:
        """Prepare lazily-created resources."""
        self.llm_service = llm_service
        self._connection_pool: AsyncConnectionPool | None = None
        self._graph: CompiledStateGraph | None = None
        self._agents: dict[str, CompiledStateGraph] = {}

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def _get_connection_pool(self) -> AsyncConnectionPool | None:
        """Open (once) the psycopg pool the checkpointer runs on.

        Deliberately separate from the SQLAlchemy engine in
        ``app/services/database.py``: the checkpointer needs ``autocommit`` and
        raw dict rows, the ORM needs neither, and sharing one pool breaks both.

        Returns:
            The open pool, or ``None`` in production when Postgres is
            unreachable — the app degrades to an unpersisted conversation rather
            than refusing to serve.

        Raises:
            Exception: Propagated outside production, where a missing
                checkpointer should fail loudly during development.
        """
        if self._connection_pool is not None:
            return self._connection_pool

        try:
            pool = AsyncConnectionPool(
                settings.checkpointer_database_uri,
                open=False,
                max_size=settings.POSTGRES_POOL_SIZE,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": None,
                    "row_factory": dict_row,
                },
            )
            await pool.open()
            self._connection_pool = pool
            return pool
        except Exception:
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _qa(self, state: RootState, config: RunnableConfig) -> Command:
        """Run the QA agent on a knowledge question.

        Reads ``messages``, ``plan``, ``macros``, ``profile`` and
        ``episodic_context``. Writes ``messages`` and ``answer``.

        Reached through the profile gate like every other branch, so ``profile``
        already carries anything the user stated this turn — which is what lets
        *"I'm 73 kg now, how much protein?"* be answered with 73 rather than with
        last week's number.

        The plan is passed in as rendered read-only text and ``QAState`` has no
        field to write a plan back into, so a knowledge question cannot mutate
        one.

        Only the answer is carried back. The agent's tool round-trip is working
        memory for this turn: replaying a ``ToolMessage`` to the next turn's
        classifier or profile extractor gains nothing, and those nodes render
        the transcript through ``dump_messages``, which cannot represent one.

        Args:
            state: Current root state.
            config: Runnable config, forwarded so agent spans nest under this
                trace.

        Returns:
            A command writing the answer and going to ``finalize``.
        """
        try:
            result = await self._agents["qa"].ainvoke(
                {
                    "messages": state.messages,
                    "plan_context": _render_plan_context(state.plan, state.macros),
                    "semantic_context": _render_semantic_context(state.profile),
                    "episodic_context": state.episodic_context,
                },
                config,
            )
        except Exception:
            # Every model in the registry has already been tried by the agent's
            # fallback middleware. The turn still owes the user a sentence.
            return Command(update={"answer": FAILURE_ANSWER}, goto="finalize")

        # An empty last message means the agent stopped on its call limit before
        # writing anything. Nothing failed, so this is not the failure wording —
        # but the turn still owes the user a sentence.
        answer = message_text(result["messages"][-1]) or EXHAUSTED_ANSWER
        return Command(
            update={"messages": [AIMessage(content=answer)], "answer": answer},
            goto="finalize",
        )

    async def _ask_missing(self, state: RootState, config: RunnableConfig) -> Command:
        """Ask for every outstanding profile field at once.

        Reads ``missing_fields``. Writes ``answer``.

        Deterministic rather than an LLM call, for two reasons: the question
        must cover **all** missing fields in one turn rather than
        trickling them out one at a time, and a fixed wording means a user who
        answers half of them sees the same question again for the rest.

        Args:
            state: Current root state.
            config: Runnable config. Unused — no I/O.

        Returns:
            A command writing the question and going to ``finalize``.
        """
        labels = [FIELD_LABELS.get(field, field) for field in state.missing_fields]

        question = (
            "Before I can put a plan together I need a few things:\n\n"
            + "\n".join(f"- {label}" for label in labels)
            + "\n\nYou can answer them all in one message."
        )
        return Command(update={"answer": question}, goto="finalize")

    async def _intent_branch(self, state: RootState, config: RunnableConfig) -> Command:
        """Route a gated turn to the branch that handles its intent.

        Reads ``intent``. Writes nothing.

        The graph's only branch point, and a lookup rather than a decision: the
        classifier already made the judgment, and keeping the step deterministic
        is what makes everything upstream of it unskippable. An intent with no
        target answers honestly instead of being routed somewhere that would
        invent a result.

        Args:
            state: Current root state.
            config: Runnable config. Unused — no I/O.

        Returns:
            A command going to the node registered for the intent.
        """
        if state.intent is None:
            logger.warning("routing_branch_without_intent")
            return Command(goto=INTENT_TARGETS["general_qa"])

        target = INTENT_TARGETS.get(state.intent, "not_implemented")
        logger.info("routing_branched", intent=state.intent, target=target)
        return Command(goto=target)

    async def _ingest_plan(self, state: RootState, config: RunnableConfig) -> Command:
        """Parse a plan the user pasted in, so the verifiers have something to score.

        Reads ``messages``. Writes ``submitted_plan`` and ``issues``.

        Writes to ``submitted_plan``, never to ``plan``.
        The distinction is the whole point of this branch: the user
        pasted someone else's programme to ask an opinion, and writing it to
        ``plan`` would replace the plan they actually follow with one they were
        only curious about.

        When the message carries no plan at all, the user's own saved plan is
        assessed instead — *"is my plan any good?"* is a real question and this
        is the only branch that can answer it, because it is the only one that
        runs the verifiers. Reading it into ``submitted_plan`` keeps that
        distinction intact and costs nothing: ``check`` is read-only, so no path
        from here reaches ``snapshot``.

        The fallback is on "nothing plan-shaped was found", not on
        "``submitted_plan`` is empty". A message that did carry a plan the
        parser could not read leaves ``unresolved`` or ``incomplete`` behind, and
        answering that with a review of a different plan would look like an
        answer to what they pasted.

        Args:
            state: Current root state.
            config: Runnable config, forwarded so subgraph spans nest.

        Returns:
            A command going to ``calc_macro`` when there is something to assess,
            and to ``ask_clarify_plan`` otherwise.
        """
        result = await self._agents["ingest"].ainvoke(
            {
                "messages": state.messages,
                "catalog": load_catalog(),
                "submitted_plan": None,
                "unresolved": [],
                "incomplete": [],
            },
            config,
        )

        submitted = result.get("submitted_plan")
        unresolved = result.get("unresolved") or []
        incomplete = result.get("incomplete") or []

        if submitted is None or not submitted.get("days"):
            nothing_was_pasted = not unresolved and not incomplete
            if nothing_was_pasted and state.plan:
                logger.info("ingest_falling_back_to_saved_plan")
                return Command(
                    update={"submitted_plan": state.plan, "issues": [_reviewing_saved_plan_note()]},
                    goto="calc_macro",
                )

            return Command(
                update={"submitted_plan": None, "issues": _ingest_notes(unresolved, incomplete)},
                goto="ask_clarify_plan",
            )

        # Some lines resolved and some did not. The plan is assessed on what was
        # understood, and the rest is reported — an assessment that quietly
        # ignores three exercises is worse than one that names them.
        return Command(
            update={
                "submitted_plan": submitted,
                "issues": _ingest_notes(unresolved, incomplete),
            },
            goto="calc_macro",
        )

    async def _ask_clarify_plan(self, state: RootState, config: RunnableConfig) -> Command:
        """Ask about the parts of the pasted plan that could not be read.

        Reads ``issues``. Writes ``answer``.

        Deterministic. A missing set count is a low-confidence exercise match or a
        missing set count is a question, not something to assume — and the
        question has to name exactly what was unclear to be answerable.

        Args:
            state: Current root state.
            config: Runnable config. Unused.

        Returns:
            A command writing the question and going to ``finalize``.
        """
        notes = [issue for issue in state.issues if issue["rubric_ref"].startswith("ingest.")]
        if not notes:
            return Command(update={"answer": _NO_PLAN_FOUND_ANSWER}, goto="finalize")

        return Command(
            update={
                "answer": (
                    "I couldn't read all of that plan well enough to review it:\n\n"
                    + "\n".join(f"- {issue['message']}" for issue in notes)
                    + "\n\nCan you clarify those and paste it again?"
                )
            },
            goto="finalize",
        )

    async def _resolve_version(self, state: RootState, config: RunnableConfig) -> Command:
        """Work out which saved version the user wants to go back to.

        Reads ``messages``. Writes ``version_index`` and ``revert_target``.

        The version index is loaded here rather than carried in state from an
        earlier turn: a plan may have been saved in a different session, and the
        list the user is choosing from must be the current one.

        Args:
            state: Current root state.
            config: Runnable config, read for ``user_id``.

        Returns:
            A command going to ``load_snapshot`` when the version is
            unambiguous, and to ``ask_which_version`` otherwise.
        """
        user_id = (config.get("metadata") or {}).get("user_id")
        if not user_id:
            return Command(
                update={"answer": _NO_HISTORY_ANSWER, "version_index": []}, goto="finalize"
            )

        index = await version_index(int(user_id))
        query = next(
            (
                message.content
                for message in reversed(state.messages)
                if getattr(message, "type", "") == "human"
            ),
            "",
        )

        version_id, reason = await resolve_version_id(str(query), index)
        if version_id is None:
            return Command(
                update={"version_index": index, "revert_target": None},
                goto="ask_which_version",
            )

        return Command(
            update={"version_index": index, "revert_target": version_id}, goto="load_snapshot"
        )

    async def _ask_which_version(self, state: RootState, config: RunnableConfig) -> Command:
        """Show the saved versions and ask the user to pick one.

        Reads ``version_index``. Writes ``answer``.

        Deterministic. The list is the answer, and a model paraphrasing it could
        drop or reorder an entry the user is trying to choose between.

        Args:
            state: Current root state.
            config: Runnable config. Unused.

        Returns:
            A command writing the question and going to ``finalize``.
        """
        index = state.version_index
        if len(index) <= 1:
            return Command(update={"answer": _NO_HISTORY_ANSWER}, goto="finalize")

        return Command(
            update={
                "answer": (
                    "I'm not sure which version you mean. Here's what I have saved, "
                    "newest first:\n\n" + render_versions(index) + "\n\nWhich one?"
                )
            },
            goto="finalize",
        )

    async def _load_snapshot(self, state: RootState, config: RunnableConfig) -> Command:
        """Load the chosen version's plan back out of Postgres.

        Reads ``revert_target``. Writes ``draft_plan`` and ``issues``.

        The snapshot becomes a *draft*, not the plan. It still passes through
        ``calc_macro``, all three verifiers and the confirm gate, because a plan
        that was valid when it was saved may not be valid now: the user may have
        lost weight, or declared an injury that did not exist then.

        Args:
            state: Current root state.
            config: Runnable config. Unused — the lookup is by id.

        Returns:
            A command going to ``calc_macro``, or to ``compose_answer`` when the
            version has disappeared.
        """
        version = await get_version(state.revert_target or "")
        if version is None:
            return Command(
                update={
                    "answer": "I couldn't find that version any more.",
                    "revert_target": None,
                },
                goto="finalize",
            )

        return Command(
            update={
                "draft_plan": dict(version.plan),
                "issues": [
                    _restore_note(
                        version.label,
                        describe_verification_reason(
                            version.profile_hash, profile_hash(state.profile)
                        ),
                    )
                ],
            },
            goto="calc_macro",
        )

    async def _patch_plan(self, state: RootState, config: RunnableConfig) -> Command:
        """Apply the requested change to the approved plan.

        Reads ``plan``, ``changes`` and ``profile``. Writes ``draft_plan`` and
        ``issues``.

        Goes to ``calc_macro`` like the build branch does, and for the same
        reason: an extra session raises TDEE, so a change that skipped the macro
        step would leave a deficit that was correct before and is wrong now.
        There is no edge from here to ``confirm``.

        Args:
            state: Current root state.
            config: Runnable config. Unused — patching is deterministic.

        Returns:
            A command going to ``calc_macro``, or to ``compose_answer`` when the
            change cannot be applied.
        """
        draft, issues = patch_plan(state.plan or {}, state.changes, state.profile, load_catalog())
        if draft is None:
            return Command(update={"issues": issues, "verdict": "fail"}, goto="compose_answer")

        return Command(update={"draft_plan": draft, "issues": issues}, goto="calc_macro")

    async def _build_diff(self, state: RootState, config: RunnableConfig) -> Command:
        """Describe what the pending change would do.

        Reads ``plan``, ``draft_plan``, ``macros`` and ``computed_macros``.
        Writes ``pending_commit``.

        Args:
            state: Current root state.
            config: Runnable config. Unused — this is a comparison.

        Returns:
            A command going to ``confirm``.
        """
        diff = build_diff(state.plan, state.draft_plan, state.macros, state.computed_macros)

        return Command(update={"pending_commit": diff}, goto="confirm")

    async def _confirm(self, state: RootState, config: RunnableConfig) -> Command:
        """Stop and ask before overwriting a plan the user already approved.

        Reads ``pending_commit``. Writes nothing.

        Implemented with ``interrupt()`` rather than by asking a question and
        hoping the next turn continues. The difference matters: an
        interrupt checkpoints the graph *here*, so the answer resumes this run
        with ``draft_plan``, ``computed_macros`` and ``issues`` intact. Asking
        conversationally would require rebuilding all of it from the transcript,
        and the plan the user approved would not be the plan they were shown.

        Args:
            state: Current root state.
            config: Runnable config. Unused.

        Returns:
            A command going to ``snapshot`` on approval, or to ``compose_answer``
            when the user declines.
        """
        diff = state.pending_commit or {}
        answer = interrupt(
            {
                "type": "confirm_change",
                "question": (
                    f"{diff.get('summary', 'This will change your plan.')}\n\n"
                    "Apply this change? Your current plan stays as it is until you say yes."
                ),
                "diff": diff,
            }
        )

        if _is_affirmative(answer):
            return Command(goto="snapshot")

        # Declined. `plan` and `macros` are untouched, so the stored plan is
        # still exactly what the user approved before this turn.
        return Command(update={"pending_commit": None, "answer": _DECLINED_ANSWER}, goto="finalize")

    async def _decline(self, state: RootState, config: RunnableConfig) -> Command:
        """Answer a message the classifier put outside the assistant's domain.

        Reads nothing. Writes ``answer``.

        The gate is one lookup and one constant, with no model between the two.
        That is the point: the alternative — asking a model to write the refusal
        — hands the off-topic message straight back to an LLM and makes the
        refusal itself a thing that can be argued with. It also cannot reach any
        node that touches the plan, because ``dispatch`` sends it here and here
        only goes to ``finalize``.

        Args:
            state: Current root state. Unused — the reply does not depend on it.
            config: Runnable config. Unused — no I/O.

        Returns:
            A command writing the refusal and going to ``finalize``.
        """
        logger.info("routing_declined_off_topic")
        return Command(update={"answer": _OFF_TOPIC_ANSWER}, goto="finalize")

    async def _not_implemented(self, state: RootState, config: RunnableConfig) -> Command:
        """Answer for the branches that are designed but not built.

        Reads ``intent``. Writes ``answer``.

        Says so plainly rather than falling through to the QA agent, which would
        produce a plausible plan full of invented numbers — the exact failure to prevent.

        Args:
            state: Current root state.
            config: Runnable config. Unused — no I/O.

        Returns:
            A command writing the explanation and going to ``finalize``.
        """
        return Command(update={"answer": _UNBUILT_BRANCH_ANSWER}, goto="finalize")

    async def _planning(self, state: RootState, config: RunnableConfig) -> Command:
        """Build a draft plan from the profile.

        Reads ``profile``. Writes ``draft_plan`` and ``issues``.

        Args:
            state: Current root state.
            config: Runnable config, forwarded so subgraph spans nest.

        Returns:
            A command going to ``calc_macro``, or to ``compose_answer`` when no
            plan could be produced at all.
        """
        result = await self._agents["planning"].ainvoke(
            {
                "profile": state.profile,
                "goal": state.profile.get("goal", "general_health"),
                "preferences": state.profile.get("preferences", ""),
                "catalog": load_catalog(),
                "template": None,
                "slots": [],
                "draft_plan": None,
                "issues": [],
            },
            config,
        )

        draft_plan = result["draft_plan"]
        issues = result["issues"]
        if draft_plan is None:
            # A conflicting constraint, already explained in `issues`. Compose
            # the answer rather than continuing into macro and verify steps that
            # have no plan to work on.
            return Command(update={"issues": issues, "verdict": "fail"}, goto="compose_answer")

        return Command(update={"draft_plan": draft_plan, "issues": issues}, goto="calc_macro")

    async def _calc_macro(self, state: RootState, config: RunnableConfig) -> Command:
        """Compute nutrition targets for the current draft plan.

        Reads ``profile`` and ``draft_plan``. Writes ``computed_macros``.

        The deliberate bottleneck of the graph: there is no path from a plan to
        an answer that skips it, which is what stops a modified plan keeping
        stale macros. It re-runs after every repair, because a swapped
        exercise can change the session count.

        Args:
            state: Current root state.
            config: Runnable config. Unused — pure arithmetic.

        Returns:
            A command going to ``verification``.

        Raises:
            KeyError: When a required profile field is absent, which means the
                profile gate let a turn through it should have stopped.
        """
        plan = state.submitted_plan or state.draft_plan or {}
        sessions = len(plan.get("days") or []) or state.profile.get("days_per_week", 3)
        macros = calc_macros(
            state.profile, sessions_per_week=sessions, goal=state.profile.get("goal", "recomp")
        )
        return Command(update={"computed_macros": macros}, goto="verification")

    async def _verification(self, state: RootState, config: RunnableConfig) -> Command:
        """Score the draft plan against all three rubrics.

        Reads ``draft_plan``, ``profile`` and ``computed_macros``. Writes
        ``issues`` and ``verdict``.

        Invoked with ``scope=[]``, which the verification graph reads as "run
        everything". A write intent does not get to narrow the checks — only a
        read-only ``check`` turn does.

        The subgraph receives no messages, and has no field to put them in.

        Args:
            state: Current root state.
            config: Runnable config, forwarded so subgraph spans nest.

        Returns:
            A command going to ``verdict_gate``.
        """
        result = await self._agents["verification"].ainvoke(
            {
                # A `check` turn assesses what the user pasted; every other
                # branch assesses the plan it just built or patched.
                "plan": state.submitted_plan or state.draft_plan or {},
                "profile": state.profile,
                "computed_macros": state.computed_macros or {},
                "catalog": load_catalog(),
                # Empty scope means "run everything", which is mandatory for a
                # write. Only `check` lets the user's wording narrow it.
                "scope": state.scope if state.intent == "check" else [],
                "rubric_version": rubric_version(),
                "issues": [],
                "verdict": None,
            },
            config,
        )
        return Command(
            update={"issues": result["issues"], "verdict": result["verdict"]},
            goto="verdict_gate",
        )

    async def _verdict_gate(self, state: RootState, config: RunnableConfig) -> Command:
        """Decide whether to repair, or to accept and move on.

        Reads ``verdict`` and ``repair_count``. Writes nothing.

        Args:
            state: Current root state.
            config: Runnable config. Unused — no I/O.

        Returns:
            A command going to ``repair``, ``build_diff``, ``snapshot`` or
            ``compose_answer``.
        """
        if state.verdict == "fail" and state.repair_count < _MAX_REPAIRS:
            return Command(goto="repair")

        if state.verdict == "fail":
            # Out of attempts. Two failed repairs usually means genuinely
            # conflicting constraints, which the user has to resolve — so the
            # issue list is presented rather than a plan being saved anyway.
            return Command(goto="compose_answer")

        # There is no edge from here to `snapshot` for it, so a `check` turn
        # cannot overwrite the plan the user actually follows.
        if state.intent in READ_ONLY_INTENTS:
            return Command(goto="compose_answer")

        # Intents that overwrite something the user already approved must
        # confirm first. A build has nothing to overwrite, so it saves directly.
        if state.intent in CONFIRM_REQUIRED_INTENTS:
            return Command(goto="build_diff")

        return Command(goto="snapshot")

    async def _repair(self, state: RootState, config: RunnableConfig) -> Command:
        """Swap the exercises that caused blocking findings.

        Reads ``draft_plan``, ``issues`` and ``profile``. Writes ``draft_plan``
        and ``repair_count``.

        ``repair_count`` lives in state because the loop crosses node
        boundaries, where a local variable does not survive. Control
        returns to ``calc_macro``, not to ``verification``: a changed plan can
        change the macros, and re-verifying against stale ones would score
        something the user is not being given.

        Args:
            state: Current root state.
            config: Runnable config. Unused — repairs are deterministic.

        Returns:
            A command going to ``calc_macro``, or to ``compose_answer`` when
            nothing could be swapped.
        """
        repaired, swaps = repair_plan(
            state.draft_plan or {}, state.issues, state.profile, load_catalog()
        )
        if swaps == 0:
            # Another pass would produce the same plan. Stop and report.
            return Command(update={"repair_count": state.repair_count + 1}, goto="compose_answer")

        return Command(
            update={"draft_plan": repaired, "repair_count": state.repair_count + 1},
            goto="calc_macro",
        )

    async def _snapshot(self, state: RootState, config: RunnableConfig) -> Command:
        """Persist the accepted plan as a new version.

        Reads ``draft_plan`` and ``computed_macros``. Writes ``plan``,
        ``macros``, ``current_version_id`` and ``version_index``.

        No ``interrupt()``: ``build_plan`` does not confirm, because
        the user has nothing to lose yet. ``change_plan`` and ``revert`` will,
        and this is where that gate attaches.

        An anonymous session skips the write and keeps the plan in state only —
        there is no user to own the row.

        Args:
            state: Current root state.
            config: Runnable config, read for ``user_id``.

        Returns:
            A command going to ``compose_answer``.
        """
        user_id = (config.get("metadata") or {}).get("user_id")
        update: dict[str, Any] = {
            "plan": state.draft_plan,
            "macros": state.computed_macros,
            "pending_commit": None,
        }

        if user_id:
            ref = await insert_version(
                user_id=int(user_id),
                plan=state.draft_plan or {},
                macros=state.computed_macros or {},
                profile_hash=profile_hash(state.profile),
                rubric_version=rubric_version(),
                # Append-only history: the version this one supersedes is
                # recorded rather than replaced, so an undo has something to
                # come back to.
                parent_id=state.current_version_id,
                # A restore is an append, not a rewind. Recording where the
                # content came from is what lets the user undo the undo — and
                # they will ("actually, put the 5-day one back").
                restored_from=state.revert_target,
                # The edge the episodic layer reads: this conversation produced
                # this plan.
                session_id=(config.get("metadata") or {}).get("session_id"),
            )
            update["current_version_id"] = ref["version_id"]
            update["version_index"] = await version_index(int(user_id))
        else:
            logger.info("snapshot_skipped_anonymous_session")

        return Command(update=update, goto="compose_answer")

    async def _compose_answer(self, state: RootState, config: RunnableConfig) -> Command:
        """Turn the plan, macros and findings into the user-facing answer.

        Reads ``draft_plan``, ``computed_macros``, ``issues`` and ``verdict``.
        Writes ``answer``.

        The model is handed pre-rendered text, not the state objects, so it can
        only describe what this node chose to show it.

        Args:
            state: Current root state.
            config: Runnable config. Callbacks propagate through contextvars.

        Returns:
            A command writing the answer and going to ``END``.
        """
        issues = sort_issues(state.issues)
        # The goal the macros were computed for, not the profile's — they are
        # the same value, and quoting the one the numbers came from is what
        # keeps the sentence and the targets below it from disagreeing.
        goal = (state.computed_macros or {}).get("goal")
        prompt = load_compose_answer_prompt(
            verdict=state.verdict or "unknown",
            plan=_render_plan(state.submitted_plan or state.draft_plan, goal),
            macros=json.dumps(state.computed_macros or {}, ensure_ascii=False),
            issues=_render_issues(issues),
        )

        try:
            response = await llm_service.call(
                [
                    SystemMessage(
                        # `episodic_context` is withheld here, and must stay
                        # withheld. This node already announced a 5-day plan as
                        # 4-day by sourcing the number from long-term memory
                        # instead of the data it was handed (docs/workflow.md
                        # every fact this prompt asks for has to come from
                        # the rendered text above it. Adding a second
                        # free-text account of the user's plan history is the
                        # same bug with more material.
                        content=load_system_prompt(
                            semantic_context=_render_semantic_context(state.profile)
                        )
                    ),
                    HumanMessage(content=prompt),
                ],
                model_name=_COMPOSER_MODEL,
            )
            answer = message_text(response)
        except Exception:
            # The plan is real and already computed; losing the prose must not
            # lose the work. Fall back to a plain rendering.
            answer = _plain_answer(
                state.submitted_plan or state.draft_plan, state.computed_macros, issues
            )

        return Command(update={"answer": answer}, goto="finalize")

    async def _finalize(self, state: RootState, config: RunnableConfig) -> Command:
        """Record this turn's answer in the transcript.

        Reads ``answer`` and ``messages``. Writes ``messages``.

        Every branch ends here, and that is the whole point. ``answer`` is what
        the facade returns to the caller, but ``messages`` is what the
        checkpointer replays: a branch that writes only ``answer`` produces a
        conversation that reloads as the user talking to themselves, with every
        reply missing. One node rather than a write in each of the nine terminal
        branches, so a branch added later cannot forget it.

        The QA branch carries the agent's ``AIMessage`` back itself, so an
        answer that is already the last message is left alone rather than
        recorded twice.

        Args:
            state: Current root state.
            config: Runnable config. Unused — no I/O.

        Returns:
            A command appending the answer and going to ``END``.
        """
        answer = state.answer
        if not answer:
            # A branch that produced no text has nothing to record. The turn is
            # still complete; the facade returns an empty message list.
            return Command(goto=END)

        last = state.messages[-1] if state.messages else None
        if isinstance(last, AIMessage) and message_text(last) == answer:
            return Command(goto=END)

        return Command(update={"messages": [AIMessage(content=answer)]}, goto=END)

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    async def create_graph(self) -> CompiledStateGraph | None:
        """Build and cache the compiled root graph.

        Runs once per process. Subgraphs are built here too, not per request.

        Returns:
            The compiled graph, or ``None`` when the checkpointer pool could not
            be opened in production.
        """
        if self._graph is not None:
            return self._graph

        try:
            self._agents = {name: build() for name, build in AGENTS.items()}

            builder = StateGraph(RootState)
            _add_nodes(builder, self)
            builder.set_entry_point("classify")

            connection_pool = await self._get_connection_pool()
            if connection_pool is not None:
                checkpointer = AsyncPostgresSaver(connection_pool)
                await checkpointer.setup()
            elif settings.ENVIRONMENT == Environment.PRODUCTION:
                checkpointer = None
            else:
                raise RuntimeError("checkpointer pool unavailable outside production")

            self._graph = builder.compile(checkpointer=checkpointer, name=GRAPH_NAME)

            return self._graph
        except Exception as e:
            logger.exception("graph_creation_failed", error=str(e))
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise

    async def _get_graph(self) -> CompiledStateGraph:
        """Return the compiled graph, building it on first use.

        Returns:
            The compiled root graph.

        Raises:
            RuntimeError: When the graph could not be created.
        """
        graph = await self.create_graph()
        if graph is None:
            raise RuntimeError("graph is unavailable — check the database connection")
        return graph

    # ------------------------------------------------------------------
    # Public facade
    # ------------------------------------------------------------------

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: str | None = None,
        username: str | None = None,
    ) -> list[Message]:
        """Process one turn and return the messages produced.

        Args:
            messages: Messages submitted this turn.
            session_id: Session id, used as the checkpointer ``thread_id``.
            user_id: Owner of the session, for trace metadata.
            username: Display name, for trace metadata.

        Returns:
            The assistant messages produced this turn. When the graph stopped at
            an ``interrupt()``, the single message is the question to answer.

        Raises:
            Exception: Propagated to the route, which maps it to a 500.
        """
        graph = await self._get_graph()
        config = self._build_config(session_id, user_id, username)

        try:
            await graph.ainvoke(await self._graph_input(graph, config, messages, user_id), config)
        except Exception as e:
            logger.exception("graph_invoke_failed", session_id=session_id, error=str(e))
            raise

        interrupt_message = await self._pending_interrupt(graph, config, session_id)
        if interrupt_message is not None:
            return [interrupt_message]

        state = await graph.aget_state(config)
        answer = state.values.get("answer", "")

        return [Message(role="assistant", content=answer)] if answer else []

    async def get_stream_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: str | None = None,
        username: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream one turn as text chunks.

        Args:
            messages: Messages submitted this turn.
            session_id: Session id, used as the checkpointer ``thread_id``.
            user_id: Owner of the session, for trace metadata.
            username: Display name, for trace metadata.

        Yields:
            Text chunks as they are produced, then the interrupt question if the
            graph stopped at a confirm gate.

        Raises:
            Exception: Propagated to the route, which closes the stream with a
                final frame.
        """
        graph = await self._get_graph()
        config = self._build_config(session_id, user_id, username)

        try:
            async for token, metadata in graph.astream(
                await self._graph_input(graph, config, messages, user_id),
                config,
                stream_mode="messages",
            ):
                # Only the answering node's tokens are user-facing. The
                # classifier emits structured output and would otherwise stream
                # raw JSON into the chat window.
                #
                # `"qa"` is the root node, not the agent's internal `model`
                # node: an agent invoked with `ainvoke` inside a node streams
                # under the *calling* node's name. Filtering on the inner name —
                # as this did while QA was a subgraph — matches nothing, and the
                # stream endpoint then yields an empty response for the one
                # branch that streams at all.
                if metadata.get("langgraph_node") != "qa":
                    continue
                chunk = message_text(token)
                if chunk:
                    yield chunk
        except Exception as e:
            logger.exception("graph_stream_failed", session_id=session_id, error=str(e))
            raise

        interrupt_message = await self._pending_interrupt(graph, config, session_id)
        if interrupt_message is not None:
            yield interrupt_message.content

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Return the conversation recorded for a session.

        Args:
            session_id: Session id used as the checkpointer ``thread_id``.

        Returns:
            The stored messages, oldest first. Empty when nothing is stored.
        """
        graph = await self._get_graph()
        state = await graph.aget_state({"configurable": {"thread_id": session_id}})
        return to_chat_messages(state.values.get("messages", []))

    async def clear_chat_history(self, session_id: str) -> None:
        """Delete every checkpoint row for a session.

        Args:
            session_id: Session id used as the checkpointer ``thread_id``.

        Raises:
            RuntimeError: When no checkpointer pool is available, so the caller
                never reports a deletion that did not happen.
        """
        await self._get_graph()
        pool = await self._get_connection_pool()
        if pool is None:
            raise RuntimeError("cannot clear history — checkpointer is unavailable")

        async with pool.connection() as conn, conn.pipeline():
            for table in settings.CHECKPOINT_TABLES:
                await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (session_id,))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_config(
        self, session_id: str, user_id: str | None, username: str | None
    ) -> RunnableConfig:
        """Assemble the runnable config for one turn.

        The Langfuse handler is attached here and only here; subgraph
        invocations inherit it, and a second handler would duplicate every span.

        Args:
            session_id: Session id, used as the checkpointer ``thread_id``.
            user_id: Owner of the session.
            username: Display name.

        Returns:
            The config to pass to every invoke and stream.
        """
        callbacks: list[BaseCallbackHandler] = get_langfuse_callbacks()
        return {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "user_id": user_id,
                "username": username,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }

    async def _graph_input(
        self,
        graph: CompiledStateGraph,
        config: RunnableConfig,
        messages: list[Message],
        user_id: str | None = None,
    ) -> Any:
        """Decide whether this turn starts a run or resumes a paused one.

        A thread parked at an ``interrupt()`` is mid-run, not finished. Feeding
        it a fresh ``{"messages": ...}`` would start a second run over the same
        state: the user's "yes" would be classified as a new request, the
        confirm gate would never receive it, and the plan they were shown would
        be rebuilt from scratch — possibly differently.

        That is the whole job. Context — profile, plan, episodes — is loaded by
        ``load_context`` inside the graph, so the facade cannot be the reason a
        turn has it, and a direct ``ainvoke`` is not a second-class caller.

        Args:
            graph: The compiled root graph.
            config: The config for this thread.
            messages: Messages submitted this turn.
            user_id: Owner of the session, or ``None`` when anonymous. Unused —
                the graph reads it from ``config``.

        Returns:
            ``Command(resume=...)`` when the thread is parked at an interrupt,
            otherwise the normal message input.
        """
        state = await graph.aget_state(config)

        if state.next and state.tasks and state.tasks[0].interrupts:
            reply = next(
                (message.content for message in reversed(messages) if message.role == "user"),
                "",
            )

            return Command(resume=reply)

        return {"messages": _to_langchain(messages)}

    async def _pending_interrupt(
        self, graph: CompiledStateGraph, config: RunnableConfig, session_id: str
    ) -> Message | None:
        """Surface an ``interrupt()`` the graph stopped at, if any.

        Checked after every invoke and stream. Without this the run looks
        complete while the graph is actually parked at a confirm gate, and the
        user is never asked the question.

        Args:
            graph: The compiled root graph.
            config: The config used for the run.
            session_id: Session id, for logging.

        Returns:
            The interrupt's question as an assistant message, or ``None`` when
            the run finished normally.
        """
        state = await graph.aget_state(config)
        if not state.next or not state.tasks or not state.tasks[0].interrupts:
            return None

        value = state.tasks[0].interrupts[0].value
        return Message(role="assistant", content=_interrupt_text(value))


def _add_nodes(builder: StateGraph, agent: "LangGraphAgent") -> None:
    """Register every root node with its declared destinations.

    Extracted from ``create_graph`` so the graph's shape is readable in one
    place, and so the routing tests can build the same topology without a
    Postgres checkpointer.

    ``destinations=`` is not decoration: it is what draws the graph and what
    makes an unreachable branch visible, so every ``goto`` a node can return
    must appear here.

    ``finalize`` is the only node with an edge to ``END``. Every branch routes
    through it so the answer it produced is recorded in ``messages`` — see
    ``LangGraphAgent._finalize``. A new terminal branch goes to ``finalize``,
    never straight to ``END``.

    Args:
        builder: The state graph to populate.
        agent: The agent whose bound node methods are being registered.
    """
    # One spine. Every turn walks the same four nodes before anything branches,
    # which is why the gate needs no guarding of its own: `check_required` is
    # the only edge into `intent_branch`, and `intent_branch` is the only edge
    # into any branch at all.
    builder.add_node("classify", classify, destinations=("load_context",))
    builder.add_node("load_context", load_context, destinations=("extract_profile",))
    builder.add_node("extract_profile", extract_profile, destinations=("check_required",))
    builder.add_node(
        "check_required", check_required, destinations=("ask_missing", "intent_branch")
    )
    builder.add_node("ask_missing", agent._ask_missing, destinations=("finalize",))
    builder.add_node(
        "intent_branch",
        agent._intent_branch,
        destinations=(*sorted(set(INTENT_TARGETS.values())), "not_implemented"),
    )

    # The QA agent — an LLM with `search_knowledge` and a prompt — enters the
    # root graph as this one node. Its own model/tool loop is internal, which is
    # why it needs no edges here beyond the one out.
    builder.add_node("qa", agent._qa, destinations=("finalize",))
    # It sits beside `qa` rather than among the plan nodes because that is the
    # whole guarantee: an off-topic turn reaches exactly one node, and that node
    # has no edge to anything that reads or writes a plan.
    builder.add_node("decline", agent._decline, destinations=("finalize",))
    builder.add_node(
        "ingest_plan", agent._ingest_plan, destinations=("calc_macro", "ask_clarify_plan")
    )
    builder.add_node("ask_clarify_plan", agent._ask_clarify_plan, destinations=("finalize",))
    builder.add_node(
        "resolve_version",
        agent._resolve_version,
        destinations=("load_snapshot", "ask_which_version", "finalize"),
    )
    builder.add_node("ask_which_version", agent._ask_which_version, destinations=("finalize",))
    builder.add_node("load_snapshot", agent._load_snapshot, destinations=("calc_macro", "finalize"))
    builder.add_node("not_implemented", agent._not_implemented, destinations=("finalize",))

    builder.add_node("planning", agent._planning, destinations=("calc_macro", "compose_answer"))
    builder.add_node("patch_plan", agent._patch_plan, destinations=("calc_macro", "compose_answer"))
    builder.add_node("calc_macro", agent._calc_macro, destinations=("verification",))
    builder.add_node("verification", agent._verification, destinations=("verdict_gate",))
    builder.add_node(
        "verdict_gate",
        agent._verdict_gate,
        destinations=("repair", "build_diff", "snapshot", "compose_answer"),
    )
    builder.add_node("repair", agent._repair, destinations=("calc_macro", "compose_answer"))
    builder.add_node("build_diff", agent._build_diff, destinations=("confirm",))
    builder.add_node("confirm", agent._confirm, destinations=("snapshot", "finalize"))
    builder.add_node("snapshot", agent._snapshot, destinations=("compose_answer",))
    builder.add_node("compose_answer", agent._compose_answer, destinations=("finalize",))
    builder.add_node("finalize", agent._finalize, destinations=(END,))


def _ingest_notes(unresolved: list[dict], incomplete: list[str]) -> list[Issue]:
    """Report the parts of a pasted plan that could not be read.

    Carried as issues so they travel to the answer through the same channel as
    every rubric finding. That is what stops a review quietly omitting three
    exercises it did not understand and still reading as a complete assessment

    Args:
        unresolved: Exercise lines that no catalog entry matched confidently.
        incomplete: Lines missing the sets or reps the volume check needs.

    Returns:
        One ``warn`` issue per problem.
    """
    notes: list[Issue] = []

    for entry in unresolved:
        options = ", ".join(candidate["name"] for candidate in entry["candidates"])
        suffix = f" Did you mean: {options}?" if options else ""
        notes.append(
            Issue(
                source="volume",
                severity="warn",
                location=f"{entry['day']} / {entry['raw_name']}",
                message=(
                    f"I couldn't confidently identify '{entry['raw_name']}', so it was left "
                    f"out of the review.{suffix}"
                ),
                suggestion={"candidates": entry["candidates"]} if entry["candidates"] else None,
                rubric_ref="ingest.unresolved_exercise",
            )
        )

    for location in incomplete:
        notes.append(
            Issue(
                source="volume",
                severity="warn",
                location=location,
                message=(
                    "No sets or reps were given, so this exercise was left out of the volume "
                    "count rather than assumed."
                ),
                suggestion=None,
                rubric_ref="ingest.missing_prescription",
            )
        )

    return notes


def _reviewing_saved_plan_note() -> Issue:
    """Say which plan is being assessed when the user pasted none.

    Carried as an issue so it travels to the answer through the same channel as
    every rubric finding — the same reason ``_restore_note`` exists. Without it
    the review reads as an assessment of something the user just sent, and a
    report on the wrong plan is worse than a request to paste one.

    Returns:
        The note.
    """
    return Issue(
        source="volume",
        severity="info",
        location="Reviewing your saved plan",
        message=(
            "You didn't paste a plan, so this is a review of the plan I have "
            "saved for you. Paste a different one and I'll assess that instead."
        ),
        suggestion=None,
        rubric_ref="ingest.saved_plan",
    )


def _restore_note(label: str, verification_reason: str) -> Issue:
    """Record which version is being restored and whether its checks still hold.

    Carried as an ``info`` issue so it flows to ``compose_answer`` through the
    same channel as every other finding, and the answer cannot describe a
    restore without also saying what was re-checked.

    Args:
        label: The version being restored, e.g. ``"v1"``.
        verification_reason: Whether the profile has moved since it was saved.

    Returns:
        The note.
    """
    return Issue(
        source="volume",
        severity="info",
        location=f"Restoring {label}",
        message=verification_reason,
        suggestion=None,
        rubric_ref="versions.restore",
    )


def _interrupt_text(value: object) -> str:
    """Render an interrupt's payload as the message the user sees.

    An interrupt carries a structured payload so a UI can render the diff
    properly, but the chat surface must show the question — not the JSON around
    it.

    Args:
        value: Whatever the interrupting node passed to ``interrupt()``.

    Returns:
        Text to send to the user.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("question"), str):
        return value["question"]
    return json.dumps(value, ensure_ascii=False)


def _is_affirmative(answer: object) -> bool:
    """Decide whether the user approved the pending change.

    Defaults to **no**. Anything not recognised as approval — silence, a
    question, a request to change something else — leaves the stored plan alone.
    A gate that resolves ambiguity in favour of proceeding is not a gate, and
    the cost of guessing wrong here is overwriting a plan the user was happy
    with.

    Args:
        answer: Whatever the user sent to resume the interrupt.

    Returns:
        ``True`` only on a recognised affirmative.
    """
    if isinstance(answer, bool):
        return answer
    if not isinstance(answer, str):
        return False

    normalised = answer.strip().lower().rstrip(".!")
    if normalised in _AFFIRMATIVE:
        return True
    # A short reply that opens with an affirmative ("yes please", "ok, do it").
    # Anything longer is prose that may well be a question, so it is not taken
    # as consent.
    words = normalised.split()
    return bool(words) and len(words) <= 3 and words[0] in _AFFIRMATIVE


def _render_plan(plan: dict[str, Any] | None, goal: str | None = None) -> str:
    """Render a plan as compact text for the composer prompt.

    The header lines are not decoration. ``compose_answer.md`` opens the answer
    with the split, the sessions a week and the goal, and a model asked for a
    fact the data does not carry will supply one from somewhere else — long-term
    memory, or a finding that names a day of the plan it replaced. So the three
    facts that sentence needs are stated here, from the plan itself.

    Sessions a week is counted off the plan rather than read from the template
    or the profile, because those are what was *asked for*: a slot with no legal
    exercise leaves a day out, and the count the user is given must be the one
    they will actually train — the same count ``calc_macro`` fed into TDEE.

    Args:
        plan: The plan to render.
        goal: The goal its macros were computed for, when known.

    Returns:
        A three-line header, then one line per exercise grouped by day. A
        placeholder when there is no plan, so the model is never handed an empty
        section it might fill in.
    """
    if not plan or not plan.get("days"):
        return "No plan could be produced."

    template = get_template(plan.get("template_id") or "")
    lines: list[str] = [
        # A pasted plan has no template, and inventing a split name for it would
        # be the same failure this header exists to prevent.
        f"Split: {template['name'] if template else 'not from a template library'}",
        f"Sessions a week: {len(plan['days'])}",
        f"Goal: {goal or 'not stated'}",
        "",
    ]
    # Numbered, and separated by a blank line. A bare `Chest:` line is what the
    # composer ran together with the previous day's last exercise, producing an
    # answer that read as one long chest session; an ordinal the model has to
    # carry through makes two days impossible to merge into one heading.
    for index, day in enumerate(plan["days"], start=1):
        lines.append(f"Day {index} — {day['name']}:")
        for exercise in day["exercises"]:
            reps = exercise["reps"]
            rir = exercise["rir"]
            lines.append(
                f"  - {exercise['name']}: {exercise['sets']} sets x {reps[0]}-{reps[1]} reps, "
                f"RIR {rir[0]}-{rir[1]}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_issues(issues: list[Issue]) -> str:
    """Render findings for the composer prompt, most severe first.

    Args:
        issues: Already-sorted findings.

    Returns:
        One line per finding, including its rubric reference so the answer can
        be traced back to the rule that produced it.
    """
    if not issues:
        return "No findings. Every enabled check passed."

    return "\n".join(
        f"- [{issue['severity']}] {issue['location']}: {issue['message']}"
        + (
            f" Suggested: {json.dumps(issue['suggestion'], ensure_ascii=False)}"
            if issue["suggestion"]
            else ""
        )
        + f" (rule: {issue['rubric_ref']})"
        for issue in issues
    )


def _plain_answer(
    plan: dict[str, Any] | None, macros: dict[str, Any] | None, issues: list[Issue]
) -> str:
    """Render the answer without a model.

    Used when the composer call fails. The plan and macros are already computed
    and correct at that point, so the work must not be thrown away just because
    the prose step was unavailable.

    Args:
        plan: The plan.
        macros: The nutrition targets.
        issues: The findings.

    Returns:
        A plain-text answer.
    """
    parts = [_render_plan(plan, (macros or {}).get("goal"))]
    if macros:
        parts.append(
            f"\nDaily targets: {macros['kcal']} kcal "
            f"(maintenance about {macros['tdee']}), "
            f"protein {macros['protein_g']}g, fat {macros['fat_g']}g, "
            f"carbs {macros['carbs_g']}g."
        )
    if issues:
        parts.append("\nReview findings:\n" + _render_issues(issues))
    parts.append(
        "\nThis is an exercise-selection adjustment, not medical advice. "
        "Sharp, new or worsening pain is a reason to see a professional."
    )
    return "\n".join(parts)


def _to_langchain(messages: list[Message]) -> list[BaseMessage]:
    """Convert API messages into graph messages.

    Only user messages are fed in. Replaying stored assistant turns would
    duplicate them against what the checkpointer already holds.

    Args:
        messages: Messages from the request body.

    Returns:
        The user messages as LangChain messages.
    """
    return [HumanMessage(content=m.content) for m in messages if m.role == "user"]


def _render_plan_context(plan: dict[str, Any] | None, macros: dict[str, Any] | None) -> str:
    """Render the user's plan and macros as read-only text for the QA prompt.

    Args:
        plan: The approved plan, if any.
        macros: Macros belonging to that plan, if any.

    Returns:
        A compact summary, or an empty string when the user has no plan.
    """
    if not plan and not macros:
        return ""

    parts: list[str] = []
    if plan:
        parts.append(f"Plan: {json.dumps(plan, ensure_ascii=False)}")
    if macros:
        parts.append(f"Macros: {json.dumps(macros, ensure_ascii=False)}")
    return "\n".join(parts)


def _render_semantic_context(profile: dict[str, Any]) -> str:
    """Render standing facts about the user as text for a prompt.

    Derived at the point of use rather than carried in state, and that is not an
    optimisation. ``extract_profile`` merges what the user said this turn *after*
    the profile is loaded, so a string rendered at load time would be one turn
    stale — it would still say 68 kg on the turn the user says they are 73. The
    profile itself is the state; this is a view of it.

    ``preferences`` and ``unmapped_injury`` are included: they are the two fields
    that carry the user's own words, and they are the reason a knowledge answer
    can avoid suggesting the movement that hurts.

    Args:
        profile: The merged profile.

    Returns:
        One ``label: value`` per known field, or an empty string when nothing is
        known — the prompt loaders supply their own wording for that case.
    """
    if not profile:
        return ""

    lines: list[str] = []
    for field, value in profile.items():
        if value is None or value == "":
            continue
        # An empty list is an answer, not a blank: `injuries: []` means the user
        # said they have none, and a prompt that omits it invites the model to
        # ask again.
        rendered = (
            (", ".join(str(item) for item in value) or "none")
            if isinstance(value, list)
            else str(value)
        )
        lines.append(f"- {_SEMANTIC_LABELS.get(field, field)}: {rendered}")

    return "\n".join(lines)


agent = LangGraphAgent()

__all__ = ["GRAPH_NAME", "LangGraphAgent", "agent"]
