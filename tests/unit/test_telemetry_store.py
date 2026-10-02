"""TC-001, TC-010, TC-011, TC-012: SQLite store schema v1, retention, failures, migrations."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

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
