"""OB-013 / AC-OB-7: the optional rotating log file."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from tokli.observability.logs import (
    LOG_FILE_BACKUPS,
    LOG_FILE_MAX_BYTES,
    configure_log_file,
    log_fields,
)

KEY = "sk-ant-api03-TOKLI-CANARY-KEY-SECRET"


@pytest.fixture
def logger() -> Iterator[logging.Logger]:
    log = logging.getLogger("tokli.test.logfile")
    log.setLevel(logging.INFO)
    yield log


def detach(handler: logging.Handler) -> None:
    logging.getLogger().removeHandler(handler)
    handler.close()


def test_log_file_defaults() -> None:
    assert LOG_FILE_MAX_BYTES == 10 * 1024 * 1024 and LOG_FILE_BACKUPS == 5


def test_log_file_written_when_enabled(tmp_path: Path, logger: logging.Logger) -> None:
    path = tmp_path / "data" / "logs" / "tokli.log"
    handler = configure_log_file(path)
    try:
        log_fields(logger, logging.INFO, "request", event="request", note="àé €")
    finally:
        detach(handler)
    raw = path.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    line = json.loads(raw.decode("utf-8").splitlines()[-1])
    assert line["event"] == "request" and line["note"] == "àé €" and line["level"] == "INFO"


def test_log_file_rotates(tmp_path: Path, logger: logging.Logger) -> None:
    path = tmp_path / "logs" / "tokli.log"
    handler = configure_log_file(path, max_bytes=2000, backups=2)
    try:
        for i in range(200):
            log_fields(logger, logging.INFO, "request", event="request", i=i)
    finally:
        detach(handler)
    files = sorted(p.name for p in path.parent.iterdir())
    assert files == ["tokli.log", "tokli.log.1", "tokli.log.2"]
    assert all((path.parent / name).stat().st_size <= 2000 for name in files)


def test_log_file_rotation_failure_does_not_stop_tokli(
    tmp_path: Path, logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "logs" / "tokli.log"
    handler = configure_log_file(path, max_bytes=500, backups=2)

    def refuse(source: str, dest: str) -> None:
        raise PermissionError("held open by another process")

    handler.rotator = refuse  # type: ignore[attr-defined]
    try:
        for i in range(50):
            log_fields(logger, logging.INFO, "request", event="request", i=i)
    finally:
        detach(handler)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["i"] == 49  # still writing to the current file
    assert handler.failures >= 1  # type: ignore[attr-defined]
    assert "Logging error" not in capsys.readouterr().err


def test_log_file_rotation_with_file_held_open(tmp_path: Path, logger: logging.Logger) -> None:
    """On Windows a reader holding the file makes the rename fail; elsewhere rotation works.
    Either way logging goes on."""
    path = tmp_path / "logs" / "tokli.log"
    handler = configure_log_file(path, max_bytes=500, backups=2)
    try:
        log_fields(logger, logging.INFO, "request", event="request", i=-1)
        with path.open("rb"):
            for i in range(50):
                log_fields(logger, logging.INFO, "request", event="request", i=i)
    finally:
        detach(handler)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["i"] == 49


def test_log_file_open_failure_does_not_stop_tokli(tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    handler = configure_log_file(blocker / "logs" / "tokli.log")
    assert handler is None


def test_log_file_contains_no_credentials_or_content(
    tmp_path: Path, logger: logging.Logger
) -> None:
    path = tmp_path / "logs" / "tokli.log"
    handler = configure_log_file(path)
    try:
        log_fields(logger, logging.INFO, "request", event="request", header=f"x-api-key: {KEY}")
    finally:
        detach(handler)
    assert "TOKLI-CANARY-KEY" not in path.read_text(encoding="utf-8")
