# State design

`GraphState` as built, from the implementation-detail spec (PDF pp. 4–5). The runtime definition
lives in `src/schemas/graph.py`; this file is the spec it must match. Several fields differ from
the PDF, each flagged inline: `todo` is gone with the `write_todo` node, `extracted_facts` and
`revision_fields` are added, `ragas_score` is named for the metric rather than the library, and
`guard_blocked` / `context_complete` are gone — each was a bool that only ever restated another
field (`block_reason is not None`, `not missing_fields`); `src/schemas/graph.py` exposes
`is_blocked()` / `is_context_complete()` in their place.

```python
class GraphState(AgentState):
    # =========================
    # Input
    # =========================
    messages: Required[Annotated[list[AnyMessage], add_messages]]
    user_query: str
    user_id: str

    # =========================
    # Intent & Guard
    # =========================
    intent: Optional[Literal["coaching", "qa", "off_topic"]]
    extracted_facts: Optional[dict]   # what parse_turn read, before merge_profile folds it in
    block_reason: Optional[str]

    # =========================
    # User Context
    # =========================
    profile: Optional[dict]
    plan: Optional[dict]
    missing_fields: list[str]
    revision_fields: list[str]        # flagged for change but not restated, so still pending
    user_info_retry_count: int

    # =========================
    # Coaching
    # =========================
    coach_retry_count: int
    verification_result: Optional[dict]

    # =========================
    # HITL
    # =========================
    hitl_decision: Optional[Literal["approve", "reject"]]
    hitl_feedback: Optional[str]
    hitl_retry_count: int

    # =========================
    # QA / RAG
    # =========================
    qa_answer: Optional[str]
    retrieved_context: Optional[list[dict]]
    faithfulness_score: Optional[float]
    qa_retry_count: int

    # =========================
    # Final Output
    # =========================
    final_message: Optional[str]
```
