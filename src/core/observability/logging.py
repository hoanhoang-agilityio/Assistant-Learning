"""Process-wide logging configuration.

Before this module existed there was no logging.basicConfig/dictConfig anywhere
in src/, so log level and format were whatever the interpreter defaulted to --
effectively WARNING to stderr with no structure. settings.log_level was defined
and reported by /health, but nothing ever applied it.

Two things are provided:

* a JSON formatter, so logs are machine-parseable in production without adding
  a dependency (stdlib json only);
* a filter that stamps every record with the run_id/thread_id already tracked
  in ContextVars by core.observability.tracing, giving log lines the same
  correlation ids that Langfuse traces use.

Nothing here changes application behaviour -- it only decides how records that
were already being emitted get formatted and where they go.
"""

from __future__ import annotations

import json
import logging
import logging.config
from typing import Any

_CONFIGURED = False

# Correlation ids stamped onto every record by RunContextFilter.
_CONTEXT_RECORD_ATTRS = ("run_id", "thread_id")

# Attributes present on every LogRecord; anything else a caller attached via
# `extra=` is treated as structured context and merged into the JSON payload.
_RESERVED_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class RunContextFilter(logging.Filter):
    """Attach the current run_id/thread_id to every record.

    Imports are deferred to call time: core.observability.tracing pulls in the
    orchestration state module, and logging is configured early in startup,
    before that import chain is otherwise needed.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from core.observability.tracing import get_trace_run_id, get_trace_thread_id

            record.run_id = get_trace_run_id()
            record.thread_id = get_trace_thread_id()
        except Exception:  # pragma: no cover - never let logging break the app
            record.run_id = None
            record.thread_id = None
        return True


class JsonFormatter(logging.Formatter):
    """Render records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Always emitted, even when null, so downstream log aggregators see a
        # stable schema rather than an optional field.
        for key in _CONTEXT_RECORD_ATTRS:
            payload[key] = getattr(record, key, None)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def build_logging_config(level: str, fmt: str) -> dict[str, Any]:
    """Return the dictConfig payload, so it can be asserted on in tests."""
    formatter = (
        {"()": f"{__name__}.JsonFormatter"}
        if fmt == "json"
        else {"format": "%(asctime)s %(levelname)-8s %(name)s [run=%(run_id)s] %(message)s"}
    )
    return {
        "version": 1,
        # Loggers are created at import time all over src/ via
        # logging.getLogger(__name__); disabling them here would silence the
        # whole application.
        "disable_existing_loggers": False,
        "filters": {"run_context": {"()": f"{__name__}.RunContextFilter"}},
        "formatters": {"default": formatter},
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
                "filters": ["run_context"],
            }
        },
        "root": {"level": level.upper(), "handlers": ["stdout"]},
    }


def configure_logging(level: str = "INFO", fmt: str = "json", *, force: bool = False) -> None:
    """Apply the process-wide logging configuration.

    Idempotent: repeated calls are ignored unless `force` is set, so importing
    the API app more than once in a single process cannot stack duplicate
    handlers onto the root logger.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    logging.config.dictConfig(build_logging_config(level, fmt))
    _CONFIGURED = True


def reset_logging_configuration() -> None:
    """Clear the idempotency latch (tests only)."""
    global _CONFIGURED
    _CONFIGURED = False
