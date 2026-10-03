"""Structured, content-safe logging (OB-006, OB-007, OB-010, TOKLI_OBSERVABILITY §5 and §6).

Log records carry structured fields in ``extra={"tokli": {...}}``. A redaction filter masks
anything that looks like a credential, as defence in depth: callers never pass credentials.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import re
import sys
import time
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import IO, Any

REQUEST_LOGGER = "tokli.request"
MAX_LINE = 8192
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # OB-013
LOG_FILE_BACKUPS = 5
_RETRY_ROTATION_S = 60.0

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


class SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating file that never stops Tokli (OB-013).

    On Windows a rename fails while another process holds the file open. Then the handler keeps
    appending to the current file, counts the failure and retries the rotation a minute later.
    Write errors are counted, never printed: stderr logging is unaffected.
    """

    def __init__(self, path: Path, max_bytes: int, backups: int) -> None:
        super().__init__(
            path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=False
        )
        self.failures = 0
        self._retry_at = 0.0

    def _open(self) -> TextIOWrapper:
        # LF line endings on every OS, so the file reads the same everywhere.
        stream = open(self.baseFilename, self.mode, encoding=self.encoding, newline="\n")  # noqa: SIM115
        assert isinstance(stream, TextIOWrapper)
        return stream

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if time.monotonic() < self._retry_at:
            return False
        return bool(super().shouldRollover(record))

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError:
            self.failures += 1
            self._retry_at = time.monotonic() + _RETRY_ROTATION_S
            if self.stream is None or self.stream.closed:
                self.stream = self._open()

    def handleError(self, record: logging.LogRecord) -> None:
        self.failures += 1


def configure_log_file(
    path: Path, *, max_bytes: int = LOG_FILE_MAX_BYTES, backups: int = LOG_FILE_BACKUPS
) -> SafeRotatingFileHandler | None:
    """Adds a JSON-lines rotating file to the root logger (OB-013). ``None`` when the file
    cannot be opened; logging to stderr goes on regardless."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = SafeRotatingFileHandler(path, max_bytes, backups)
    except OSError:
        return None
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    return handler
