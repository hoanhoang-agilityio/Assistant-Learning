# State design

Literal `GraphState` schema from the implementation-detail spec (PDF pp. 4–5). The runtime
definition lives in `app/schemas/graph.py`; this file is the spec it must match.

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
    guard_blocked: bool
    block_reason: Optional[str]

    # =========================
    # User Context
    # =========================
    profile: Optional[dict]
    plan: Optional[dict]
    context_complete: bool
    missing_fields: list[str]

    # =========================
    # Coaching
    # =========================
    todo: Optional[list[dict]]
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
    ragas_score: Optional[float]
    qa_retry_count: int

    # =========================
    # Final Output
    # =========================
    final_message: Optional[str]
```
