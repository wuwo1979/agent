"""
Structured logging with request_id tracing.

Usage:
    from core.structured_log import get_request_id, setup_structured_logging

    # At server start
    setup_structured_logging()

    # In any handler
    rid = get_request_id()  # auto-generated per-request
    logger.info("Tool called", extra={"tool": "read_file", "duration_ms": 42})
"""

import contextvars
import json
import logging
import os
import time
import uuid

# Per-request (or per-thread) request_id — contextvars for async, fallback threading.local
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_request_start_var: contextvars.ContextVar[float] = contextvars.ContextVar("request_start", default=0.0)


def generate_request_id() -> str:
    """Generate a short, unique request ID for tracing."""
    return uuid.uuid4().hex[:12]


def set_request_id(rid: str = ""):
    """Set request_id for current context. Auto-generate if empty."""
    if not rid:
        rid = generate_request_id()
    _request_id_var.set(rid)


def get_request_id() -> str:
    """Get current request_id from context."""
    return _request_id_var.get()


def set_request_start(t: float = 0.0):
    """Set request start time."""
    if t <= 0:
        t = time.perf_counter()
    _request_start_var.set(t)


def get_request_elapsed_ms() -> float:
    """Get elapsed ms since request start."""
    start = _request_start_var.get()
    if start <= 0:
        return 0.0
    return round((time.perf_counter() - start) * 1000, 1)


class JSONStructuredHandler(logging.Handler):
    """
    JSON-structured logging handler for stderr.

    Output format (one line per record):
    {"t":"2026-06-27T10:30:00","rid":"a1b2c3d4e5f6","mod":"mcp_gateway.transport","lvl":"INFO",
     "msg":"STDIO initialized","dur_ms":0,"err":""}
    """

    def __init__(self, stream=None):
        super().__init__()
        import sys
        self.stream = stream or sys.stderr

    def format(self, record: logging.LogRecord) -> str:
        # Get request_id from context (fallback to record-level if available)
        rid = get_request_id() or getattr(record, "request_id", "")
        elapsed = get_request_elapsed_ms()
        duration = getattr(record, "duration_ms", elapsed)

        entry = {
            "t": self._format_time(record.created),
            "rid": rid,
            "mod": record.name,
            "lvl": record.levelname,
            "msg": record.getMessage(),
        }

        # Optional fields
        if duration:
            entry["dur_ms"] = duration
        if record.exc_info and record.exc_info[1]:
            entry["err"] = str(record.exc_info[1])

        # Extra fields from record (e.g., extra={"tool": "read_file"})
        extras = {k: v for k, v in record.__dict__.items()
                  if k not in ("args", "asctime", "created", "exc_info", "exc_text",
                               "filename", "funcName", "levelname", "levelno",
                               "lineno", "message", "module", "msecs",
                               "msg", "name", "pathname", "process", "processName",
                               "relativeCreated", "stack_info", "thread", "threadName")}
        if extras:
            entry["ext"] = extras

        return json.dumps(entry, ensure_ascii=False, default=str)

    @staticmethod
    def _format_time(timestamp: float) -> str:
        """Format timestamp as ISO 8601 without timezone overhead."""
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _install_structured_handler():
    """
    Install JSON structured handler on the root logger.
    Replaces existing stderr handlers with structured output.
    """
    root = logging.getLogger()

    # Remove existing stderr handlers
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler):
            root.removeHandler(h)

    # Add structured JSON handler
    handler = JSONStructuredHandler()
    root.addHandler(handler)

    # Set level from env or default to INFO
    level_name = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    # Ensure all module loggers propagate to root
    for name in list(logging.root.manager.loggerDict):
        logger_obj = logging.getLogger(name)
        logger_obj.handlers.clear()
        logger_obj.propagate = True


def setup_structured_logging():
    """
    Set up structured JSON logging.

    Call once at server start:
        setup_structured_logging()
        logger = logging.getLogger("mcp_gateway.server")
        logger.info("Server started")
    """
    _install_structured_handler()
    logger = logging.getLogger("core.structured_log")
    logger.info("Structured JSON logging initialized")


# Backward-compatible: ensure INFO level by default if not yet configured
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
