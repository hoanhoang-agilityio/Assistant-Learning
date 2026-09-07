"""Structured logging setup.

Exposes a single configured ``logger``. Event names are ``lowercase_with_underscores``
and variables are passed as keyword arguments so they stay filterable — never f-strings.

``bind_context`` writes into structlog's contextvar store, so a ``user_id`` bound inside
an auth dependency appears on every later log line for that request without being threaded
through call signatures. ``clear_context`` must run at the end of each request, or the
values leak into the next one served by the same worker.
"""

import logging
import sys
from typing import Any

import structlog

from src.configs.config import settings


def configure_logging() -> None:
    """Configure structlog and the stdlib logging bridge.

    Renders JSON in staging/production and a coloured console format in development,
    selected by ``settings.LOG_FORMAT``.
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )

    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.LOG_FORMAT == "console"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def bind_context(**kwargs: Any) -> None:
    """Attach key/value pairs to every subsequent log line in this request."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Drop all bound context. Call at the end of every request."""
    structlog.contextvars.clear_contextvars()


configure_logging()

logger: structlog.stdlib.BoundLogger = structlog.get_logger(settings.PROJECT_NAME)

__all__ = ["bind_context", "clear_context", "configure_logging", "logger"]
