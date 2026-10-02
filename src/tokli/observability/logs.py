"""Structured, content-safe logging (OB-006, OB-007, OB-010, TOKLI_OBSERVABILITY §5 and §6).

Log records carry structured fields in ``extra={"tokli": {...}}``. A redaction filter masks
anything that looks like a credential, as defence in depth: callers never pass credentials.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import IO, Any

REQUEST_LOGGER = "tokli.request"
MAX_LINE = 8192

_SECRETS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)(bearer\s+)[^\s\"',;]+"),
    re.compile(r"(?i)((?:x-api-key|api[_-]?key|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;]+"),
]


def redact(text: str) -> str:
    for pattern in _SECRETS:
        text = pattern.sub(
            lambda m: (m.group(1) if m.re.groups else "") + "[redacted]",
            text,
        )
    return text


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    extra = getattr(record, "tokli", None)
    return dict(extra) if isinstance(extra, dict) else {}


def _limit(line: str) -> str:
    if len(line) <= MAX_LINE:
        return line
    return line[: MAX_LINE - 20] + "…[truncated]"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_fields(record))
        return _limit(redact(json.dumps(payload, ensure_ascii=True, default=str)))


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = " ".join(f"{k}={v}" for k, v in _fields(record).items())
        ts = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="seconds")
        return _limit(redact(f"{ts} {record.levelname} {record.getMessage()} {fields}".rstrip()))


def configure_logging(fmt: str, stream: IO[str] | None = None) -> logging.Handler:
    """Adds one handler to the root logger and returns it (callers may remove it)."""
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    return handler


def log_fields(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"tokli": fields})
