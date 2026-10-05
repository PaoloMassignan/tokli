"""TC-001, TC-010, TC-011, TC-012: SQLite store schema v1, retention, failures, migrations."""

from __future__ import annotations

import importlib
import sqlite3
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, replace
from pathlib import Path
from types import ModuleType

import pytest

from tokli.telemetry.records import CompressorStatsRecord, RequestRecord
from tokli.telemetry.store import SCHEMA_VERSION, SchemaError, TelemetryStore

RECORD = RequestRecord(
    request_id="01TEST0000000000000000000A",
    ts_start="2026-09-30T10:00:00.000+00:00",
    ts_end="2026-09-30T10:00:01.000+00:00",
    provider="anthropic",
    protocol="anthropic_messages",
    endpoint="/v1/messages",
    model="claude-x",
    stream=True,
    auth_mode="passthrough",
    credential_kind="api_key",
    policy="LOSSLESS_ONLY",
    config_hash="abc",
    outcome="compressed",
    passthrough_reason=None,
    segments_total=5,
    segments_mutable=3,
    segments_changed=1,
    tokenizer_id="tiktoken:o200k_base@446a9538cb6c",
    est_original_tokens=100,
    est_forwarded_tokens=80,
    status_code=200,
    ms_parse=1.0,
    ms_pipeline=2.0,
    ms_render=0.5,
    ms_upstream_ttfb=100.0,
    ms_upstream_total=900.0,
    ms_tokli_overhead=4.0,
    ms_total=904.0,
)
STATS = CompressorStatsRecord(
    request_id=RECORD.request_id,
    compressor_id="json_minify",
    compressor_version="1",
    kind="LOSSLESS",
    considered=3,
    applicable=1,
    accepted=1,
    rejected_no_gain=0,
    rejected_invariant=0,
    failed=0,
    skipped_budget=0,
    tokens_in=100,
    tokens_out=80,
    marginal_saved=20,
    ms_total=0.7,
    skip_reasons={"too_small": 2},
)


def open_store(path: Path, retention_days: int = 30) -> TelemetryStore:
    store = TelemetryStore(path, retention_days)
    store.start()
    return store


def test_records_round_trip(tmp_path: Path) -> None:
    store = open_store(tmp_path / "t.db")
    store.submit(RECORD, [STATS])
    store.flush()
    got = store.get(RECORD.request_id)
    store.close()
    assert got is not None
    assert got["record"]["outcome"] == "compressed" and got["record"]["ms_total"] == 904.0
    assert got["record"]["history_rewritten"] is False and got["record"]["reference_stubs"] == 0
    assert got["compressors"][0]["skip_reasons"] == {"too_small": 2}
    assert store.healthy


def test_schema_version_recorded(tmp_path: Path) -> None:
    store = open_store(tmp_path / "t.db")
    store.close()
    with sqlite3.connect(tmp_path / "t.db") as db:
        assert db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone() == (
            str(SCHEMA_VERSION),
        )


def test_schema_migration_forward(tmp_path: Path) -> None:
    open_store(tmp_path / "t.db").close()
    open_store(tmp_path / "t.db").close()  # reopening the current version is fine
    with sqlite3.connect(tmp_path / "t.db") as db:
        db.execute("UPDATE meta SET value = '99' WHERE key = 'schema_version'")
    with pytest.raises(SchemaError) as info:
        TelemetryStore(tmp_path / "t.db", 30).start()
    assert "99" in str(info.value) and "newer" in str(info.value)


def test_retention_pruning(tmp_path: Path) -> None:
    store = open_store(tmp_path / "t.db", retention_days=30)
    old = replace(
        RECORD, request_id="01OLD00000000000000000000A", ts_start="2026-08-01T00:00:00.000+00:00"
    )
    store.submit(old, [replace(STATS, request_id=old.request_id)])
    store.submit(RECORD, [STATS])
    store.flush()
    assert store.prune(now_iso="2026-09-30T12:00:00+00:00") == 1
    assert store.get(old.request_id) is None
    assert store.get(RECORD.request_id) is not None
    store.close()


def test_retention_zero_keeps_everything(tmp_path: Path) -> None:
    store = open_store(tmp_path / "t.db", retention_days=0)
    old = replace(RECORD, ts_start="2020-01-01T00:00:00.000+00:00")
    store.submit(old, [])
    store.flush()
    assert store.prune(now_iso="2026-09-30T12:00:00+00:00") == 0
    store.close()


def test_non_ascii_data_dir(tmp_path: Path) -> None:
    store = open_store(tmp_path / "Usér données" / "t.db")
    store.submit(RECORD, [STATS])
    store.flush()
    assert store.get(RECORD.request_id) is not None
    store.close()


def test_write_failure_counts_and_never_raises(tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    store = TelemetryStore(blocker / "t.db", 30)  # the directory cannot be created
    store.start()
    store.submit(RECORD, [STATS])
    store.flush()
    assert not store.healthy
    assert store.failures >= 1
    store.close()


def test_request_record_pruning_fields(tmp_path: Path) -> None:
    store = open_store(tmp_path / "t.db")
    store.submit(replace(RECORD, history_rewritten=True, reference_stubs=2), [STATS])
    store.flush()
    got = store.get(RECORD.request_id)
    store.close()
    assert got is not None
    assert got["record"]["history_rewritten"] is True and got["record"]["reference_stubs"] == 2


def _write_v1_database(path: Path) -> None:
    """A database exactly as an S1 build wrote it: schema v1, without `header_names` (v2) and
    `tokens_in_accepted` (v3)."""
    from dataclasses import asdict, fields

    from tokli.telemetry.store import _REQUEST_TYPES, _STATS_TYPES

    columns = [f.name for f in fields(RequestRecord) if f.name != "header_names"]
    stats_columns = [
        f.name for f in fields(CompressorStatsRecord) if f.name != "tokens_in_accepted"
    ]
    row = {k: v for k, v in asdict(RECORD).items() if k in columns}
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO meta VALUES ('schema_version', '1')")
        db.execute(
            "CREATE TABLE requests ("
            + ", ".join(
                f"{c} {_REQUEST_TYPES[c]}" + (" PRIMARY KEY" if c == "request_id" else "")
                for c in columns
            )
            + ")"
        )
        db.execute(
            f"INSERT INTO requests ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [row[c] for c in columns],
        )
        db.execute(
            "CREATE TABLE compressor_stats ("
            + ", ".join(f"{c} {_STATS_TYPES[c]}" for c in stats_columns)
            + ", PRIMARY KEY (request_id, compressor_id))"
        )
    sqlite3.connect(path).close()


def test_schema_migration_forward_from_v1(tmp_path: Path) -> None:
    """AC-TC-9 / ADR 0005, ADR 0007: a v1 database is migrated in place; nothing earlier is
    lost."""
    path = tmp_path / "t.db"
    _write_v1_database(path)
    store = open_store(path)
    old = store.get(RECORD.request_id)
    new = replace(RECORD, request_id="01NEW00000000000000000000A", header_names=("x-api-key",))
    store.submit(new, [])
    store.flush()
    got = store.get(new.request_id)
    store.close()
    assert SCHEMA_VERSION == 4
    assert old is not None and old["record"]["header_names"] is None
    assert old["record"]["est_original_tokens"] == 100 and old["record"]["ms_total"] == 904.0
    assert got is not None and got["record"]["header_names"] == ["x-api-key"]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone() == (
            "4",
        )
        assert db.execute("SELECT COUNT(*) FROM requests").fetchone() == (2,)
        columns = {row[1] for row in db.execute("PRAGMA table_info(compressor_stats)")}
        assert "tokens_in_accepted" in columns


def test_header_names_persisted(tmp_path: Path) -> None:
    """OB-012 / AC-OB-6: names survive a restart; values are never stored."""
    path = tmp_path / "t.db"
    store = open_store(path)
    store.submit(replace(RECORD, header_names=("anthropic-version", "x-api-key")), [])
    store.close()
    reopened = open_store(path)
    got = reopened.get(RECORD.request_id)
    reopened.close()
    assert got is not None
    assert got["record"]["header_names"] == ["anthropic-version", "x-api-key"]


def test_usage_and_calibration_fields_round_trip(tmp_path: Path) -> None:
    store = open_store(tmp_path / "t.db")
    record = replace(
        RECORD,
        usage_source="provider_partial",
        usage_input=25,
        usage_cache_read=30000,
        usage_cache_write_5m=1000,
        usage_cache_write_1h=200,
        usage_output=1,
        calibration_k=1.25,
        est_request_tokens_original=26000,
        est_request_tokens_forwarded=25000,
    )
    store.submit(record, [])
    store.flush()
    got = store.get(RECORD.request_id)
    store.close()
    assert got is not None
    stored = got["record"]
    assert stored["usage_source"] == "provider_partial" and stored["usage_cache_read"] == 30000
    assert stored["calibration_k"] == 1.25 and stored["est_request_tokens_forwarded"] == 25000


# --- S4.5 D2 (TC-001, TC-012; review A2): a column's SQL type follows its field's annotation.

_EXPECTED_SQL = {
    "int": "INTEGER",
    "int | None": "INTEGER",
    "bool": "INTEGER",
    "float": "REAL",
    "float | None": "REAL",
    "str": "TEXT",
    "str | None": "TEXT",
    "tuple[str, ...] | None": "TEXT",  # JSON
    "dict[str, int]": "TEXT",  # JSON
}


def _declared_types(path: Path, table: str) -> dict[str, str]:
    with sqlite3.connect(path) as db:
        return {row[1]: row[2] for row in db.execute(f"PRAGMA table_info({table})")}


@pytest.mark.parametrize(
    "record_type, table",
    [(RequestRecord, "requests"), (CompressorStatsRecord, "compressor_stats")],
)
def test_existing_column_types_unchanged(tmp_path: Path, record_type: type, table: str) -> None:
    """Every current field maps to the SQL type of its annotation, so the fix changes no
    existing column and needs no schema version bump."""
    open_store(tmp_path / "t.db").close()
    declared = _declared_types(tmp_path / "t.db", table)
    for f in fields(record_type):
        assert declared[f.name] == _EXPECTED_SQL[str(f.type)], f.name


@pytest.fixture
def store_with(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[type], ModuleType]]:
    """Reloads the store module with an extended `RequestRecord`, then restores it."""
    import tokli.telemetry.records as records
    import tokli.telemetry.store as store_module

    def load(extended: type) -> ModuleType:
        monkeypatch.setattr(records, "RequestRecord", extended)
        return importlib.reload(store_module)

    yield load
    monkeypatch.undo()
    importlib.reload(store_module)


def test_column_type_follows_field_annotation(
    tmp_path: Path, store_with: Callable[[type], ModuleType]
) -> None:
    """Root cause: `_sql_type` chose the type from the column's name (prefixes and hand-written
    lists), so a new integer field with an unforeseen name was created as TEXT, and the forward
    migration never retypes a column."""

    @dataclass(frozen=True)
    class Extended(RequestRecord):
        retries_seen: int | None = None
        share_kept: float | None = None

    module = store_with(Extended)
    store = module.TelemetryStore(tmp_path / "t.db", 30)
    store.start()
    store.close()
    declared = _declared_types(tmp_path / "t.db", "requests")
    assert declared["retries_seen"] == "INTEGER"
    assert declared["share_kept"] == "REAL"


def test_unmapped_annotation_is_refused(store_with: Callable[[type], ModuleType]) -> None:
    """A field type with no SQL mapping fails loudly instead of falling back to TEXT."""

    @dataclass(frozen=True)
    class Extended(RequestRecord):
        odd: frozenset[int] | None = None

    with pytest.raises(TypeError, match="odd"):
        store_with(Extended)


def test_close_never_closes_the_connection_under_a_busy_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-011: closing the store while the writer thread is still busy loses no record and
    never touches the connection from two threads.

    Root cause: `close()` waited for the writer at most a fixed time, then closed the SQLite
    connection even if the writer was still using it. On a slow machine the writer was in the
    middle of an INSERT, and the native library crashed (access violation)."""
    import tokli.telemetry.store as store_module

    release = threading.Event()
    real_write = TelemetryStore._write

    def slow_write(self: TelemetryStore, *args: object) -> None:
        release.wait(5)
        real_write(self, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(TelemetryStore, "_write", slow_write)
    monkeypatch.setattr(store_module, "_CLOSE_TIMEOUT_S", 0.1)
    store = open_store(tmp_path / "t.db")
    writer = store._thread
    assert writer is not None
    store.submit(RECORD, [STATS])
    store.close()  # returns while the writer still waits
    release.set()
    writer.join(5)
    assert not writer.is_alive()
    assert store.failures == 0
    with sqlite3.connect(tmp_path / "t.db") as db:
        assert db.execute("SELECT COUNT(*) FROM requests").fetchone() == (1,)


V4_REQUEST = ("saved_cache_read", "saved_cache_write", "saved_input")


def test_schema_migration_v3_to_v4(tmp_path: Path) -> None:
    """TC-012, ADR 0014: a v3 database gains the saving-region columns in place; its rows keep
    every value and read the new columns as null; new rows store them."""
    from dataclasses import asdict, fields

    from tokli.telemetry.store import _REQUEST_TYPES, _STATS_TYPES

    path = tmp_path / "t.db"
    columns = [f.name for f in fields(RequestRecord) if f.name not in V4_REQUEST]
    stats_columns = [f.name for f in fields(CompressorStatsRecord) if f.name not in V4_REQUEST]
    row = {k: v for k, v in asdict(RECORD).items() if k in columns}
    row["header_names"] = None
    stat = asdict(STATS)
    stat["skip_reasons"] = "{}"
    with sqlite3.connect(path) as db:  # a database exactly as a v3 build wrote it
        db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO meta VALUES ('schema_version', '3')")
        db.execute(
            "CREATE TABLE requests ("
            + ", ".join(
                f"{c} {_REQUEST_TYPES[c]}" + (" PRIMARY KEY" if c == "request_id" else "")
                for c in columns
            )
            + ")"
        )
        db.execute(
            f"INSERT INTO requests ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            [row[c] for c in columns],
        )
        db.execute(
            "CREATE TABLE compressor_stats ("
            + ", ".join(f"{c} {_STATS_TYPES[c]}" for c in stats_columns)
            + ", PRIMARY KEY (request_id, compressor_id))"
        )
        db.execute(
            f"INSERT INTO compressor_stats ({', '.join(stats_columns)}) "
            f"VALUES ({', '.join('?' for _ in stats_columns)})",
            [stat[c] for c in stats_columns],
        )
    sqlite3.connect(path).close()
    store = open_store(path)
    old = store.get(RECORD.request_id)
    new = replace(
        RECORD,
        request_id="01NEW00000000000000000000B",
        saved_cache_read=7,
        saved_cache_write=2,
        saved_input=1,
    )
    store.submit(new, [replace(STATS, request_id=new.request_id, saved_cache_read=7)])
    store.flush()
    got = store.get(new.request_id)
    store.close()
    assert old is not None and old["record"]["saved_cache_read"] is None
    assert old["record"]["est_original_tokens"] == RECORD.est_original_tokens
    assert old["compressors"][0]["saved_input"] is None
    assert got is not None
    assert (got["record"]["saved_cache_read"], got["record"]["saved_cache_write"]) == (7, 2)
    assert got["compressors"][0]["saved_cache_read"] == 7
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone() == (
            "4",
        )
