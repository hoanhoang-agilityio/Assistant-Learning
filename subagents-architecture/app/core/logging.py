"""Structured logging with per-request context binding.

The auth layer logs events as ``logger.info("event_name", key=value)``. Those
keyword pairs only survive as separate fields under a structured logger, hence
structlog rather than stdlib logging.

``bind_context`` writes into structlog's contextvar store, so a ``user_id``
bound inside an auth dependency appears on every later log line for that same
request without being threaded through call signatures. ``clear_context`` must
run at the end of each request or values leak into the next one served by the
same worker.
"""

import logging
import sys
from typing import Any

import structlog

from app.core.configs.config import settings

_configured = False


def configure_logging() -> None:
    """Configure structlog once per process.

    Renders JSON when ``LOG_FORMAT`` is ``json``, otherwise a coloured console
    format for local development.
    """
    global _configured
    if _configured:
        return

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.LOG_FORMAT == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def bind_context(**kwargs: Any) -> None:
    """Attach key/value pairs to every subsequent log line in this request."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Drop all bound context. Call at the end of every request."""
    structlog.contextvars.clear_contextvars()


configure_logging()
logger = structlog.get_logger()

__all__ = ["bind_context", "clear_context", "configure_logging", "logger"]
