"""Chatbot endpoints.

Thin by design: log, delegate to the agent, map failures. No graph logic lives
here, and the route must never learn that the agent is made of subgraphs.

Every endpoint depends on ``get_current_session``, so a request is scoped to
exactly one conversation. The session id is the checkpointer ``thread_id``,
which means the token is what decides whose history is read or deleted.
"""

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.api.v1.auth import get_current_session
from app.core.configs.config import settings
from app.core.langgraph.graph import LangGraphAgent
from app.core.limiter import limiter
from app.models.session import Session
from app.schemas.chat import ChatRequest, ChatResponse, StreamResponse
from app.services.session_naming import maybe_name_session

router = APIRouter()
agent = LangGraphAgent()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
) -> ChatResponse:
    """Process one chat turn and return the agent's reply."""
    try:
        if settings.SESSION_NAMING_ENABLED:
            maybe_name_session(session.id, session.name, chat_request.messages)

        result = await agent.get_response(
            chat_request.messages,
            session.id,
            user_id=str(session.user_id),
            username=session.username,
        )

        return ChatResponse(messages=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to process chat request") from e


@router.post("/chat/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    session: Session = Depends(get_current_session),
) -> StreamingResponse:
    """Stream one chat turn as server-sent events."""

    # Outside event_source() on purpose: inside the generator this would not run
    # until the client starts consuming, and an abandoned stream would leave the
    # session unnamed.
    if settings.SESSION_NAMING_ENABLED:
        maybe_name_session(session.id, session.name, chat_request.messages)

    async def event_source() -> AsyncGenerator[str, None]:
        """Yield SSE frames, ending with a single ``done`` frame either way."""
        try:
            async for chunk in agent.get_stream_response(
                chat_request.messages,
                session.id,
                user_id=str(session.user_id),
                username=session.username,
            ):
                yield _frame(StreamResponse(content=chunk))
            yield _frame(StreamResponse(done=True))
        except Exception:
            # The response has already started, so the status code is committed.
            # A final done frame lets the client close cleanly instead of
            # waiting on a stream that will never end.
            yield _frame(StreamResponse(content="\n\n[the response was cut short]", done=True))

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/messages", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def get_messages(
    request: Request,
    session: Session = Depends(get_current_session),
) -> ChatResponse:
    """Return the stored conversation for this session."""
    try:
        messages = await agent.get_chat_history(session.id)
        return ChatResponse(messages=messages)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to load chat history") from e


@router.delete("/messages", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def clear_messages(
    request: Request,
    session: Session = Depends(get_current_session),
) -> None:
    """Delete the stored conversation for this session."""
    try:
        await agent.clear_chat_history(session.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to clear chat history") from e


def _frame(payload: StreamResponse) -> str:
    """Serialise one server-sent event frame.

    Args:
        payload: The frame contents.

    Returns:
        The frame as an SSE ``data:`` line pair.
    """
    return f"data: {json.dumps(payload.model_dump(mode='json'))}\n\n"


__all__ = ["router"]
