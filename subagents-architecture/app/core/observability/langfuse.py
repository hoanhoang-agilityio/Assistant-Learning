"""Langfuse tracing.

One handler for the whole process, attached once in the root graph's
``RunnableConfig``. Subgraph invocations inherit the parent config, so attaching
a second handler per agent only produces duplicate spans.

The handler is built in ``langfuse_init`` rather than at import, because the
Langfuse client it binds to must be configured from ``settings`` first — a
handler constructed before that binds to a disabled client and silently drops
every trace.

"""

from langchain_core.callbacks import BaseCallbackHandler
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from app.core.configs.config import settings
from app.core.logging import logger

_callback_handler: CallbackHandler | None = None


def langfuse_init() -> None:
    """Configure the Langfuse client and build the shared callback handler.

    Called from the application lifespan. Tracing is never allowed to break a
    request: a failed credential check logs a warning and leaves tracing off
    rather than raising.
    """
    global _callback_handler

    if not settings.LANGFUSE_TRACING_ENABLED:
        logger.info("langfuse_tracing_disabled")
        return

    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        logger.warning("langfuse_keys_missing_tracing_off", host=settings.LANGFUSE_HOST)
        return

    try:
        client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            environment=settings.ENVIRONMENT.value,
        )
        if not client.auth_check():
            logger.warning("langfuse_auth_check_failed", host=settings.LANGFUSE_HOST)
            return
        _callback_handler = CallbackHandler()
        logger.info("langfuse_initialized", host=settings.LANGFUSE_HOST)
    except Exception as e:
        logger.exception("langfuse_init_failed", host=settings.LANGFUSE_HOST, error=str(e))


def get_langfuse_callbacks() -> list[BaseCallbackHandler]:
    """Return the callbacks to attach to the root graph config.

    Returns:
        A single-element list with the shared handler, or an empty list when
        tracing is disabled or was never successfully initialised.
    """
    return [_callback_handler] if _callback_handler is not None else []


__all__ = ["get_langfuse_callbacks", "langfuse_init"]
