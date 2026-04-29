"""Structured (JSON) logging + per-rule timing for the DQ kit.

Goals:

- Every rule execution emits a single JSON line with fixed fields, so a
  downstream pipeline (Datadog, Loki, Splunk) can build dashboards without
  parsing free-form text.
- Logging is opt-in: importing this module does nothing. Callers (currently
  ``main.run_from_config``) call :func:`configure_logging` at the start of a
  run. Library consumers who don't want our logger get standard Python
  ``logging`` semantics (no handlers attached, propagate=False).
- Per-rule duration is captured by :class:`Timer` so the same number flows
  into both the rule result (``duration_ms``) and the structured log event.

Environment variables (read by :func:`configure_logging` when its arguments
are ``None``):

- ``ENTERPRISE_DQ_LOG_LEVEL`` — DEBUG / INFO / WARNING / ERROR. Default INFO.
- ``ENTERPRISE_DQ_LOG_FORMAT`` — ``json`` (default) or ``text``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

LOGGER_NAMESPACE = "enterprise_dq"

_RUN_ID: str | None = None

_LOG_RECORD_BUILTINS = {
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
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render LogRecord as a single JSON line with merged extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if _RUN_ID is not None:
            payload["run_id"] = _RUN_ID
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_BUILTINS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    level: str | None = None,
    fmt: str | None = None,
    stream=None,
) -> logging.Logger:
    """Attach a single handler to the kit's namespaced logger. Idempotent.

    Subsequent calls replace the handler set, so callers can re-configure
    inside a long-lived process (e.g. a Streamlit session) without leaking.
    """
    resolved_level = (level or os.environ.get("ENTERPRISE_DQ_LOG_LEVEL", "INFO")).upper()
    resolved_fmt = (fmt or os.environ.get("ENTERPRISE_DQ_LOG_FORMAT", "json")).lower()

    handler = logging.StreamHandler(stream or sys.stderr)
    if resolved_fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    root = logging.getLogger(LOGGER_NAMESPACE)
    root.handlers = [handler]
    root.setLevel(resolved_level)
    root.propagate = False
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the kit's namespace."""
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")


def new_run_id() -> str:
    """Generate and remember a per-run correlation id, surfaced on every log line."""
    global _RUN_ID
    _RUN_ID = uuid.uuid4().hex[:12]
    return _RUN_ID


def current_run_id() -> str | None:
    return _RUN_ID


def reset_run_id() -> None:
    """Test helper: clear the cached run id."""
    global _RUN_ID
    _RUN_ID = None


class Timer:
    """Wall-clock timer producing milliseconds rounded to 2 decimals.

    Usage::

        with Timer() as t:
            do_work()
        print(t.duration_ms)
    """

    __slots__ = ("_start", "duration_ms")

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        self.duration_ms = 0.0
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.duration_ms = round((time.perf_counter() - self._start) * 1000, 2)
