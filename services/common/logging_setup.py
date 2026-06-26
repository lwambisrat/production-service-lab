"""
Shared structured logging helpers used by all three services.

Why this exists:
  The assignment requires structured JSON logs that can answer
  "what happened, when, which service, which request, what outcome".
  Rather than duplicate a logger into every service, all three
  import from here so the log format is identical everywhere.

Usage:
  from common.logging_setup import get_logger, log_event

  logger = get_logger("ride-booking")
  log_event(logger, "ride_request_received", "Ride request received", request_id, "INFO",
            ride_id="RIDE-001", customer="Lwam")
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats every log record as a single JSON object on stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level":     record.levelname,
            "service":   getattr(record, "service", record.name),
            "event":     getattr(record, "event", "log"),
            "message":   record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }

        # Merge any extra structured fields the caller attached
        for key, value in record.__dict__.items():
            if key not in (
                "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno",
                "funcName", "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process", "name", "message",
                "taskName", "service", "event", "request_id",
            ):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def get_logger(service_name: str) -> logging.Logger:
    """Return a JSON-structured logger for the given service name."""
    logger = logging.getLogger(service_name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    message: str,
    request_id: str,
    level: str = "INFO",
    **fields,
) -> None:
    """
    Emit a structured log event.

    Args:
        logger:     Logger returned by get_logger()
        event:      Machine-readable snake_case event tag (e.g. "ride_request_received")
        message:    Human-readable description
        request_id: Trace ID propagated across the entire request chain
        level:      INFO | WARNING | ERROR
        **fields:   Any additional structured context (ride_id, driver_id, etc.)
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(
        log_level,
        message,
        extra={"event": event, "request_id": request_id, **fields},
    )
