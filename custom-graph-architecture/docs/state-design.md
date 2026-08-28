# State design

`GraphState` as built for the supervisor-orchestrated workflow (see
[`supervisor-migration.md`](supervisor-migration.md) §1 M1). The runtime definition lives in
`src/schemas/graph.py`; this file mirrors it. This supersedes the intent-routed shape the PDF
spec (pp. 4–5) describes. `is_context_complete()` and `HitlDecision` existed in
`src/schemas/graph.py` only to keep the old fixed-pipeline schema import-clean for
`src/core/langgraph/`; both were removed along with it at the Milestone 11 cutover (28/08).

Differences from the fixed-pipeline schema, each a consequence of the supervisor replacing
`parse_turn`'s upfront classification with a per-hop routing decision: `user_query` is gone —
the transcript is the input, read fresh each hop; `intent`/`extracted_facts` are gone with
`parse_turn` — `next` is the supervisor's own routing decision instead, and profile facts arrive
as `user_agent`'s tool-call arguments, never as a batch-extracted structured read;
`missing_fields`/`revision_fields`/`user_info_retry_count` are gone — `coach_agent` computes
completeness on the fly from `profile` (§4 of the migration doc: no state field for it) and
`user_agent` asks conversationally, no persistent nag counter; `hitl_decision` /`hitl_feedback`/
`hitl_retry_count` are renamed and generalized to `approval_decision`/`approval_feedback`/
`approval_retry_count`, shared by the coach's plan and `user_agent`'s profile overwrites via
`pending_approval`; `final_message` is gone — the reply is the last `AIMessage` in `messages`;
`iteration_count` and `summary` are new, for the supervisor's hop cap and `summarize`'s
transcript compression.

```python
class GraphState(AgentState):
    # =========================
    # Input
    # =========================
    messages: Required[Annotated[list[AnyMessage], add_messages]]
    user_id: str

    # =========================
    # Guard
    # =========================
    block_reason: Optional[str]

    # =========================
    # Supervisor loop
    # =========================
    next: Optional[Literal["user_agent", "coach_agent", "qa_agent", "FINISH"]]
    iteration_count: int
    summary: str

    # =========================
    # User Context
    # =========================
    profile: Optional[dict]
    plan: Optional[dict]

    # =========================
    # Coaching
    # =========================
    coach_retry_count: int
    verification_result: Optional[dict]

    # =========================
    # Shared approval — coach's plan, or user_agent's profile overwrite
    # =========================
    pending_approval: Optional[PendingApproval]  # TypedDict: source, kind, summary, payload
    approval_decision: Optional[Literal["approve", "reject"]]
    approval_feedback: Optional[str]
    approval_retry_count: int

    # =========================
    # QA / RAG
    # =========================
    qa_answer: Optional[str]
    retrieved_context: Optional[list[RetrievedChunk]]
    faithfulness_score: Optional[float]
    qa_retry_count: int
```

`PendingApproval` (`TypedDict`): `source: Literal["coach_agent", "user_agent"]`,
`kind: Literal["plan", "profile_update"]`, `summary: str`, `payload: dict`. Staged by
`present_plan` (`source="coach_agent"`) or `update_user_profile` (`source="user_agent"`) before
routing to `hitl_agent`, and read back by `route_after_hitl` to decide which of the six outcomes
applies.

Agent context objects — `CoachContext`, `QaContext`, `UserAgentContext` — carry `user_id` (and,
for the coach and QA agents, `profile`) into each agent's tools without putting them in
`GraphState`; they are constructed fresh per invocation, not persisted across turns.
