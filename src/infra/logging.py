"""Structured logging with per-request context.

Usage:
    from src.infra.logging import get_logger, request_id_ctx

    logger = get_logger(__name__)
    logger.info("event happened", extra={"event": "cache_hit", "key_type": "search"})

The request_id_ctx ContextVar is set by the request-ID middleware in api.py
and is automatically included in every log record emitted during that request.
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any

# Set by the request-ID middleware on every incoming request
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class _JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON for easy machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
        }
        request_id = request_id_ctx.get("")
        if request_id:
            payload["request_id"] = request_id

        # Merge any extra fields passed via `extra={...}`
        skip = {
            "args", "asctime", "created", "exc_info", "exc_text", "filename",
            "funcName", "levelname", "levelno", "lineno", "message", "module",
            "msecs", "msg", "name", "pathname", "process", "processName",
            "relativeCreated", "stack_info", "taskName", "thread", "threadName",
        }
        for key, value in record.__dict__.items():
            if key not in skip:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _configure_root_logger() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
