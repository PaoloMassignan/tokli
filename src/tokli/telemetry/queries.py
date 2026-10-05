"""Read-only queries over the telemetry database (SPEC 015, ADR 0006).

Every call opens its own read-only connection, so metrics reads never share a connection with the
writer thread and never block it (WAL allows concurrent readers). A missing database file reads
as empty.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUEST_COLUMNS = (
    "request_id",
    "ts_start",
    "provider",
    "protocol",
    "model",
    "stream",
    "policy",
    "config_hash",
    "outcome",
    "passthrough_reason",
    "status_code",
    "est_original_tokens",
    "est_forwarded_tokens",
    "est_request_tokens_original",
    "est_request_tokens_forwarded",
    "usage_source",
    "usage_input",
    "usage_cache_read",
    "usage_cache_write_5m",
    "usage_cache_write_1h",
    "calibration_k",
    "ms_tokli_overhead",
    "usage_output",
    "credential_kind",
    "history_rewritten",
    "saved_cache_read",  # schema v4 (TC-017)
    "saved_cache_write",
    "saved_input",
)
STATS_COLUMNS = (
    "request_id",
    "compressor_id",
    "kind",
    "considered",
    "applicable",
    "accepted",
    "failed",
    "skipped_budget",
    "tokens_in",
    "tokens_out",
    "marginal_saved",
    "ms_total",
    "tokens_in_accepted",
    "saved_cache_read",  # schema v4 (TC-017)
    "saved_cache_write",
    "saved_input",
)


def iso(moment: datetime) -> str:
    """The stored timestamp format (UTC, milliseconds), so range filters compare as strings."""
    return moment.astimezone(UTC).isoformat(timespec="milliseconds")


@contextmanager
def read_only(path: Path) -> Iterator[sqlite3.Connection | None]:
    if not path.is_file():
        yield None
        return
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        yield conn
    finally:
        conn.close()


def requests_between(path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    with read_only(path) as conn:
        if conn is None:
            return []
        rows = conn.execute(
            f"SELECT {', '.join(REQUEST_COLUMNS)} FROM requests "
            "WHERE ts_start >= ? AND ts_start < ?",
            (iso(start), iso(end)),
        ).fetchall()
    return [dict(zip(REQUEST_COLUMNS, row, strict=True)) for row in rows]


def stats_between(path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    columns = ", ".join(f"s.{c}" for c in STATS_COLUMNS)
    with read_only(path) as conn:
        if conn is None:
            return []
        rows = conn.execute(
            f"SELECT {columns} FROM compressor_stats s JOIN requests r USING (request_id) "
            "WHERE r.ts_start >= ? AND r.ts_start < ?",
            (iso(start), iso(end)),
        ).fetchall()
    return [dict(zip(STATS_COLUMNS, row, strict=True)) for row in rows]


STATS_REQUEST_COLUMNS = (
    "outcome",
    "calibration_k",
    "provider",
    "model",
    "ts_start",  # S6: what pricing a compressor's saving needs (API-013)
    "credential_kind",
    "usage_source",
    "usage_input",
    "usage_cache_read",
    "usage_cache_write_5m",
    "usage_cache_write_1h",
    "usage_output",
)


def stats_with_request(path: Path, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Stats rows with the few request fields needed to attribute them (one query)."""
    names = (*STATS_COLUMNS, *STATS_REQUEST_COLUMNS)
    columns = ", ".join(
        [*(f"s.{c}" for c in STATS_COLUMNS), *(f"r.{c}" for c in STATS_REQUEST_COLUMNS)]
    )
    with read_only(path) as conn:
        if conn is None:
            return []
        rows = conn.execute(
            f"SELECT {columns} FROM compressor_stats s JOIN requests r USING (request_id) "
            "WHERE r.ts_start >= ? AND r.ts_start < ?",
            (iso(start), iso(end)),
        ).fetchall()
    return [dict(zip(names, row, strict=True)) for row in rows]


def recent_requests(path: Path, limit: int, cursor: str | None) -> list[dict[str, Any]]:
    """Newest first by request id (ULIDs sort by time); ``cursor`` excludes it and newer."""
    with read_only(path) as conn:
        if conn is None:
            return []
        where, args = ("WHERE request_id < ? ", (cursor,)) if cursor else ("", ())
        rows = conn.execute(
            f"SELECT {', '.join(REQUEST_COLUMNS)} FROM requests {where}"
            "ORDER BY request_id DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
    return [dict(zip(REQUEST_COLUMNS, row, strict=True)) for row in rows]
