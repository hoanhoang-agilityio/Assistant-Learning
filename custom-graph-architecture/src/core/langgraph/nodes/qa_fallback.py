"""The ``qa_fallback`` node: no answer could be grounded in the knowledge base, so stop."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState, RetrievedChunk

QA_FALLBACK_NO_CONTEXT = (
    "I couldn't find enough reliable information in my knowledge base to answer this "
    "question accurately. Rather than provide an answer I'm not confident in, I'll "
    "leave it here."
)

QA_FALLBACK_UNSUPPORTED = (
    "I found some relevant information, but it wasn't sufficient to support a reliable "
    "answer to your question. Rather than make assumptions or go beyond the available "
    "information, I'll leave it here."
)

QA_FALLBACK_OUTRO = (
    "You can try rephrasing your question or narrowing it down, and I'll take another "
    "look. If your question involves pain, an injury, or a medical symptom, please "
    "consult a qualified doctor or physiotherapist rather than relying solely on this guidance."
)


class QaFallbackUpdate(TypedDict):
    """The state ``qa_fallback`` writes."""

    qa_answer: None
    final_message: str
    messages: list[AnyMessage]


def build_qa_fallback_message(retrieved_context: list[RetrievedChunk] | None) -> str:
    """Compose the message that ends a QA run no trusted answer came out of."""

    intro = QA_FALLBACK_UNSUPPORTED if retrieved_context else QA_FALLBACK_NO_CONTEXT

    return f"{intro}\n\n{QA_FALLBACK_OUTRO}"


async def qa_fallback(state: GraphState) -> QaFallbackUpdate:
    """End the run after the answer failed the faithfulness gate too many times."""

    message = build_qa_fallback_message(state.get("retrieved_context"))

    return {
        "qa_answer": None,
        "final_message": message,
        "messages": [AIMessage(content=message)],
    }
