"""What each node is called when the user is watching it run.

Only the nodes worth showing are listed. A node whose whole job is to produce a message
the user is about to read anyway — every terminal node, the interrupt gate — would
narrate itself twice, and the guard's internals are not something to describe to the
person being screened. Anything absent from this table is streamed as no step at all.
"""

from src.enums import Node

STEP_LABELS: dict[Node, str] = {
    Node.GUARD_INPUT: "Checking your message",
    Node.COACH_AGENT: "Building your plan",
    Node.DRAFT_PROFILE: "Reading what you've told me",
    Node.DETERMINISTIC_VERIFICATION: "Checking the plan against the safety and volume rules",
    Node.PRESENT_PLAN: "Writing your plan up",
    Node.QA_AGENT: "Searching the knowledge base",
    Node.VERIFY_FAITHFULNESS: "Checking the answer against its sources",
}

__all__ = ["STEP_LABELS"]
