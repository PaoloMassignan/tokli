"""SQLite telemetry store, schema v3 (TC-001, TC-002, TC-010, TC-011, TC-012; ADR 0003, 0005,
0007).

Writes happen on one background thread through a bounded queue, so the request path never waits
for the disk. A failing write never breaks traffic: it is counted, the store reports unhealthy,
and a warning is logged at most once per minute.
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
import time
from collections.abc import Sequence
from dataclasses import asdict, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tokli.telemetry.records import CompressorStatsRecord, RequestRecord

SCHEMA_VERSION = 3
_LOG = logging.getLogger("tokli.telemetry")
_WARN_INTERVAL_S = 60.0

_REQUEST_COLUMNS = [f.name for f in fields(RequestRecord)]
_STATS_COLUMNS = [f.name for f in fields(CompressorStatsRecord)]
_BOOL_COLUMNS = {"stream", "history_rewritten"}
_JSON_COLUMNS = {"header_names"}


def _sql_type(name: str) -> str:
    if name.startswith(("ms_", "calibration")) or name in {"ms_total"}:
        return "REAL"
    if name in {"stream", "history_rewritten"} or name.startswith(
        ("segments_", "est_", "usage_input", "usage_cache", "usage_output", "usage_reasoning")
    ):
        return "INTEGER"
    if name in {
        "status_code",
        "reference_stubs",
        "considered",
        "applicable",
        "accepted",
        "rejected_no_gain",
        "rejected_invariant",
        "failed",
        "skipped_budget",
        "tokens_in",
        "tokens_out",
        "marginal_saved",
        "tokens_in_accepted",
    }:
        return "INTEGER"
    return "TEXT"


_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS requests ("
    + ", ".join(
        f"{c} {_sql_type(c)}" + (" PRIMARY KEY" if c == "request_id" else "")
        for c in _REQUEST_COLUMNS
    )
    + ")",
    "CREATE INDEX IF NOT EXISTS requests_ts ON requests (ts_start)",
    "CREATE TABLE IF NOT EXISTS compressor_stats ("
    + ", ".join(f"{c} {_sql_type(c)}" for c in _STATS_COLUMNS)
    + ", PRIMARY KEY (request_id, compressor_id))",
]

_STOP = object()


def _migrate(conn: sqlite3.Connection) -> None:
    """Forward migration (TC-012, ADR 0005): add every missing column; never drop or retype."""
    for table, columns in (("requests", _REQUEST_COLUMNS), ("compressor_stats", _STATS_COLUMNS)):
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for column in columns:
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {_sql_type(column)}")


class SchemaError(Exception):
    """The database was written by a newer, unknown schema version."""


class TelemetryStore:
    def __init__(self, path: Path, retention_days: int, *, queue_size: int = 10_000) -> None:
        self._path = path
        self._retention_days = retention_days
        self._queue: queue.Queue[object] = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._failures = 0
        self._healthy = True
        self._last_warning = 0.0
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._last_prune = 0.0

    # -- lifecycle -----------------------------------------------------------------------------

    def start(self) -> None:
        """Opens (or creates) the database and starts the writer. A newer schema is refused.

        Idempotent: a second call does nothing.
        """
        if self._thread is not None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
        except (OSError, sqlite3.Error) as exc:
            self._fail(f"cannot open telemetry database {self._path}: {exc}")
        else:
            self._conn = conn
            self._check_schema(conn)
            try:
                with self._lock, conn:
                    conn.execute("PRAGMA journal_mode=WAL")
                    for statement in _SCHEMA:
                        conn.execute(statement)
                    _migrate(conn)
                    conn.execute(
                        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                        (str(SCHEMA_VERSION),),
                    )
            except sqlite3.Error as exc:
                self._fail(f"cannot initialise telemetry database {self._path}: {exc}")
            self.prune()
        self._thread = threading.Thread(target=self._run, name="tokli-telemetry", daemon=True)
        self._thread.start()

    def _check_schema(self, conn: sqlite3.Connection) -> None:
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        except sqlite3.Error:
            return  # a new database: no meta table yet
        if row is not None and int(row[0]) > SCHEMA_VERSION:
            conn.close()
            self._conn = None
            raise SchemaError(
                f"telemetry database {self._path} has schema version {row[0]}, newer than this "
                f"Tokli ({SCHEMA_VERSION}); use a newer Tokli or another --data-dir"
            )

    def close(self) -> None:
        if self._thread is not None:
            self._queue.put(_STOP)
            self._thread.join(timeout=10)
            self._thread = None
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # -- writing -------------------------------------------------------------------------------

    def submit(self, record: RequestRecord, stats: Sequence[CompressorStatsRecord]) -> None:
        try:
            self._queue.put_nowait((record, tuple(stats)))
        except queue.Full:
            self._fail("telemetry queue full; record dropped")

    def flush(self, timeout_s: float = 5.0) -> None:
        done = threading.Event()
        try:
            self._queue.put(done, timeout=timeout_s)
        except queue.Full:
            return
        done.wait(timeout_s)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            if isinstance(item, threading.Event):
                item.set()
                continue
            if isinstance(item, tuple) and len(item) == 2:
                record: RequestRecord = item[0]
                stats: tuple[CompressorStatsRecord, ...] = item[1]
                self._write(record, stats)
            if time.monotonic() - self._last_prune > 24 * 3600:
                self.prune()

    def _write(self, record: RequestRecord, stats: Sequence[CompressorStatsRecord]) -> None:
        conn = self._conn
        if conn is None:
            self._fail("telemetry database unavailable")
            return
        row = asdict(record)
        for column in _JSON_COLUMNS:
            if row[column] is not None:
                row[column] = json.dumps(list(row[column]))
        try:
            with self._lock, conn:
                conn.execute(
                    f"INSERT OR REPLACE INTO requests ({', '.join(_REQUEST_COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in _REQUEST_COLUMNS)})",
                    [row[c] for c in _REQUEST_COLUMNS],
                )
                for stat in stats:
                    values = asdict(stat)
                    values["skip_reasons"] = json.dumps(values["skip_reasons"], sort_keys=True)
                    conn.execute(
                        f"INSERT OR REPLACE INTO compressor_stats ({', '.join(_STATS_COLUMNS)}) "
                        f"VALUES ({', '.join('?' for _ in _STATS_COLUMNS)})",
                        [values[c] for c in _STATS_COLUMNS],
                    )
        except sqlite3.Error as exc:
            self._fail(f"telemetry write failed: {exc}")
        else:
            self._healthy = True

    def _fail(self, message: str) -> None:
        self._failures += 1
        self._healthy = False
        now = time.monotonic()
        if now - self._last_warning >= _WARN_INTERVAL_S or self._last_warning == 0.0:
            self._last_warning = now
            _LOG.warning(
                "telemetry sink failing",
                extra={"tokli": {"event": "telemetry_failure", "detail": message}},
            )

    # -- state and queries ---------------------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def retention_days(self) -> int:
        return self._retention_days

    def set_retention(self, days: int) -> None:
        """A UI change of `telemetry.retention_days` (CF-009); applied at the next prune."""
        self._retention_days = days

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def failures(self) -> int:
        return self._failures

    def prune(self, now_iso: str | None = None) -> int:
        """Deletes records older than ``retention_days`` (0 keeps all). Returns rows removed."""
        self._last_prune = time.monotonic()
        if self._retention_days == 0 or self._conn is None:
            return 0
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
        cutoff = (now - timedelta(days=self._retention_days)).isoformat(timespec="milliseconds")
        try:
            with self._lock, self._conn as conn:
                old = [
                    r[0]
                    for r in conn.execute(
                        "SELECT request_id FROM requests WHERE ts_start < ?", (cutoff,)
                    )
                ]
                conn.executemany(
                    "DELETE FROM compressor_stats WHERE request_id = ?", [(r,) for r in old]
                )
                conn.executemany("DELETE FROM requests WHERE request_id = ?", [(r,) for r in old])
        except sqlite3.Error as exc:
            self._fail(f"telemetry retention failed: {exc}")
            return 0
        return len(old)

    def get(self, request_id: str) -> dict[str, Any] | None:
        if self._conn is None:
            return None
        try:
            with self._lock:
                cursor = self._conn.execute(
                    f"SELECT {', '.join(_REQUEST_COLUMNS)} FROM requests WHERE request_id = ?",
                    (request_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                stats = self._conn.execute(
                    f"SELECT {', '.join(_STATS_COLUMNS)} FROM compressor_stats "
                    "WHERE request_id = ?",
                    (request_id,),
                ).fetchall()
        except sqlite3.Error:
            return None
        record = dict(zip(_REQUEST_COLUMNS, row, strict=True))
        for column in _BOOL_COLUMNS:
            record[column] = bool(record[column])
        for column in _JSON_COLUMNS:
            if record[column] is not None:
                record[column] = json.loads(record[column])
        compressors = []
        for stat in stats:
            entry = dict(zip(_STATS_COLUMNS, stat, strict=True))
            entry["skip_reasons"] = json.loads(entry["skip_reasons"] or "{}")
            compressors.append(entry)
        return {"record": record, "compressors": compressors}
