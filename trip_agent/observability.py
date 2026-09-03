from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOGGER_NAME = "trip_agent"
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "bearer_token",
    "cookie",
    "key",
    "refresh_token",
    "secret",
    "token",
}


def _redact(value: Any, key: str = "") -> Any:
    normalized_key = key.lower().replace("-", "_")
    if (
        normalized_key in _SENSITIVE_KEYS
        or normalized_key.endswith("_api_key")
        or normalized_key.endswith("_secret")
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(name): _redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value) > 4000:
        return f"{value[:4000]}...[TRUNCATED {len(value) - 4000} chars]"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def close_logging() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)
    if hasattr(logger, "_trip_agent_target"):
        delattr(logger, "_trip_agent_target")


def configure_logging(path: str | Path) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    target = str(Path(path).resolve())
    if getattr(logger, "_trip_agent_target", None) == target:
        return logger

    close_logging()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    logger._trip_agent_target = target
    return logger


def log_event(event: str, **fields: Any) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        return
    record = {
        "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "event": event,
        **fields,
    }
    logger.info(json.dumps(_redact(record), ensure_ascii=False, separators=(",", ":")))
