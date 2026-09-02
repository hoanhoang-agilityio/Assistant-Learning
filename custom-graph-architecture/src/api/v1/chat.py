"""Chat endpoints: log, delegate to the graph, map failures. No graph logic lives here."""

import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from src.api.v1.auth import get_current_session
from src.configs.config import settings
from src.enums import StreamEventType
from src.middlewares import limiter
from src.models.session import Session
from src.runtime.facade import langgraph_runtime
from src.schemas import ChatRequest, ChatResponse, StreamResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat"][0])
async def chat(
    request: Request,
    chat_request: ChatRequest,
    session: Annotated[Session, Depends(get_current_session)],
) -> ChatResponse:
    """Process one chat turn and return the graph's reply."""
    try:
        messages, form = await langgraph_runtime.get_response(
            chat_request.messages,
            session.id,
            user_id=str(session.user_id),
            form_data=chat_request.form_data,
        )
        return ChatResponse(messages=messages, form=form)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to process chat request"
        ) from e


@router.post("/chat/stream")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["chat_stream"][0])
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    session: Annotated[Session, Depends(get_current_session)],
) -> StreamingResponse:
    """Stream one chat turn as server-sent events: a frame per step, then per reply."""

    async def event_source() -> AsyncGenerator[str]:
        try:
            async for event in langgraph_runtime.get_stream_response(
                chat_request.messages,
                session.id,
                user_id=str(session.user_id),
                form_data=chat_request.form_data,
            ):
                yield _frame(event)
            yield _frame(StreamResponse(type=StreamEventType.DONE, done=True))
        except Exception:
            yield _frame(
                StreamResponse(
                    type=StreamEventType.DONE,
                    content="\n\n[the response was cut short]",
                    done=True,
                )
            )

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/messages", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def get_messages(
    request: Request,
    session: Annotated[Session, Depends(get_current_session)],
) -> ChatResponse:
    """Return the stored conversation for this session."""
    try:
        messages = await langgraph_runtime.get_chat_history(session.id)
        return ChatResponse(messages=messages)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to load chat history"
        ) from e


@router.delete("/messages", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["messages"][0])
async def clear_messages(
    request: Request,
    session: Annotated[Session, Depends(get_current_session)],
) -> None:
    """Delete the stored conversation for this session."""
    try:
        await langgraph_runtime.clear_chat_history(session.id)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Failed to clear chat history"
        ) from e


def _frame(payload: StreamResponse) -> str:
    """Serialise one server-sent event frame."""
    return f"data: {json.dumps(payload.model_dump(mode='json'))}\n\n"


__all__ = ["router"]
