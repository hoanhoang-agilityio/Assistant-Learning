"""Structured logging setup.

Exposes a single configured ``logger``. Event names are ``lowercase_with_underscores``
and variables are passed as keyword arguments so they stay filterable — never f-strings.
"""

import logging
import sys

import structlog

from src.core.configs.config import settings


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


configure_logging()

logger: structlog.stdlib.BoundLogger = structlog.get_logger(settings.PROJECT_NAME)
