"""Structured logging — text by default, JSON when CKG_LOG_FORMAT=json.

Every log record carries an ISO timestamp and the logger name. JSON mode is
designed for ingestion by Loki / CloudWatch / Datadog without re-parsing.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Render every record as one JSON object on its own line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Allow arbitrary structured fields via logger.info("...", extra={...})
        for key, value in record.__dict__.items():
            if key in ("args", "asctime", "created", "exc_info", "exc_text",
                       "filename", "funcName", "levelname", "levelno",
                       "lineno", "message", "module", "msecs", "msg", "name",
                       "pathname", "process", "processName", "relativeCreated",
                       "stack_info", "thread", "threadName"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(debug: bool = False, fmt: str = "text") -> None:
    """Wire the root logger. Idempotent — safe to call multiple times."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # Remove any pre-existing handlers so re-init doesn't double-log
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
                datefmt="%H:%M:%S",
            )
        )
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper so every module imports from one place."""
    return logging.getLogger(name)
