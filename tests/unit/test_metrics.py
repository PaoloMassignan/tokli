"""SPEC 013 TC-013, TC-015, TC-016 and SPEC 015 API-010, API-011: metrics use cases on a real
SQLite store with hand-built records (values computed by hand in each test)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tokli.app.metrics import InvalidParameters, MetricsQuery, parse_filters
from tokli.telemetry.records import CompressorStatsRecord, RequestRecord
from tokli.telemetry.store import TelemetryStore

BASE = RequestRecord(
    request_id="01TEST00000000000000000000",
    ts_start="2026-10-01T10:00:00.000+00:00",
    ts_end="2026-10-01T10:00:01.000+00:00",
    provider="anthropic",
    protocol="anthropic_messages",
    endpoint="/v1/messages",
    model="claude-x",
    stream=True,
    auth_mode="passthrough",
    credential_kind="api_key",
    policy="LOSSLESS_ONLY",
    config_hash="hash-a",
    outcome="passthrough",
    passthrough_reason=None,
    segments_total=3,
    segments_mutable=2,
    segments_changed=0,
    tokenizer_id="tiktoken:o200k_base@x",
    est_original_tokens=None,
    est_forwarded_tokens=None,
    status_code=200,
    ms_parse=0.1,
    ms_pipeline=0.1,
    ms_render=None,
    ms_upstream_ttfb=100.0,
    ms_upstream_total=900.0,
    ms_tokli_overhead=2.0,
    ms_total=902.0,
)
WINDOW = {"from": "2026-10-01T00:00:00Z", "to": "2026-10-02T00:00:00Z"}


def stats(request_id: str, cid: str = "json_minify", kind: str = "LOSSLESS", **values: Any):  # type: ignore[no-untyped-def]
    row: dict[str, Any] = {
        "considered": 1,
        "applicable": 1,
        "accepted": 1,
        "rejected_no_gain": 0,
        "rejected_invariant": 0,
        "failed": 0,
        "skipped_budget": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "marginal_saved": 0,
        "ms_total": 0.0,
        "tokens_in_accepted": 0,
    }
    row.update(values)
    return CompressorStatsRecord(
        request_id=request_id, compressor_id=cid, compressor_version="1", kind=kind, **row
    )


def write(path: Path, items: list[tuple[RequestRecord, list[CompressorStatsRecord]]]) -> None:
    store = TelemetryStore(path, retention_days=0)
    store.start()
    for record, rows in items:
        store.submit(record, rows)
    store.close()


def mixed_traffic() -> list[tuple[RequestRecord, list[CompressorStatsRecord]]]:
    """r1 calibrated (k 1.1), r2 outlier (k 3), r3 pass-through without usage, r4 verbatim
    route, r5 upstream 429 without any figure."""
    r1 = replace(
        BASE,
        request_id="01TEST0000000000000000000A",
        outcome="compressed",
        est_original_tokens=1000,
        est_forwarded_tokens=800,
        usage_source="provider",
        usage_input=50,
        usage_cache_read=1600,
        usage_cache_write_5m=0,
        usage_cache_write_1h=0,
        usage_output=10,
        calibration_k=1.1,
        est_request_tokens_original=1700,
        est_request_tokens_forwarded=1500,
    )
    r2 = replace(
        BASE,
        request_id="01TEST0000000000000000000B",
        ts_start="2026-10-01T11:00:00.000+00:00",
        outcome="compressed",
        est_original_tokens=500,
        est_forwarded_tokens=400,
        usage_source="provider",
        usage_input=300,
        usage_cache_read=0,
        usage_cache_write_5m=0,
        usage_cache_write_1h=0,
        usage_output=5,
        calibration_k=3.0,
        est_request_tokens_original=200,
        est_request_tokens_forwarded=100,
    )
    r3 = replace(
        BASE,
        request_id="01TEST0000000000000000000C",
        ts_start="2026-10-01T12:00:00.000+00:00",
        passthrough_reason="no_applicable_compressor",
        est_original_tokens=300,
        est_forwarded_tokens=300,
        est_request_tokens_original=900,
        est_request_tokens_forwarded=900,
    )
    r4 = replace(
        BASE,
        request_id="01TEST0000000000000000000D",
        ts_start="2026-10-01T13:00:00.000+00:00",
        protocol=None,
        endpoint="/v1/models",
        outcome="verbatim_route",
        model=None,
    )
    r5 = replace(
        BASE,
        request_id="01TEST0000000000000000000E",
        ts_start="2026-10-01T14:00:00.000+00:00",
        status_code=429,
        passthrough_reason="no_applicable_compressor",
    )
    return [
        (
            r1,
            [
                stats(
                    r1.request_id,
                    considered=5,
                    applicable=4,
                    accepted=2,
                    failed=1,
                    tokens_in=1000,
                    tokens_out=850,
                    marginal_saved=150,
                    ms_total=2.0,
                    tokens_in_accepted=600,
                ),
                stats(
                    r1.request_id,
                    cid="fake_b",
                    kind="LOSSY",
                    tokens_in=200,
                    tokens_out=150,
                    marginal_saved=50,
                    ms_total=0.5,
                    tokens_in_accepted=200,
                ),
            ],
        ),
        (
            r2,
            [
                stats(
                    r2.request_id,
                    considered=3,
                    applicable=2,
                    accepted=1,
                    tokens_in=400,
                    tokens_out=300,
                    marginal_saved=100,
                    ms_total=1.0,
                    tokens_in_accepted=250,
                )
            ],
        ),
        (r3, [stats(r3.request_id, considered=2, applicable=0, accepted=0)]),
        (r4, []),
        (r5, []),
    ]


@pytest.fixture
def query(tmp_path: Path) -> MetricsQuery:
    write(tmp_path / "t.db", mixed_traffic())
    return MetricsQuery(tmp_path / "t.db")


def filters(**extra: str):  # type: ignore[no-untyped-def]
    return parse_filters({**WINDOW, **extra})


def test_summary_totals_hand_computed(query: MetricsQuery) -> None:
    """AC-TC-11 / TC-015."""
    result = query.summary(filters())
    assert result["requests"] == {
        "total": 5,
        "measured": 3,
        "by_outcome": {"compressed": 2, "passthrough": 2, "verbatim_route": 1},
    }
    tokens = result["tokens"]
    # forwarded: 1650 (exact) + 300 (exact) + 900 (estimate)
    assert tokens["forwarded"] == {
        "value": 2850,
        "method": "estimate",
        "exact_share": round(1950 / 2850, 4),
    }
    # saved: 220 (calibrated, 200 x 1.1) + 100 (estimate, k out of range) + 0 (exact, pass-through)
    assert tokens["saved"] == {
        "value": 320,
        "method": "estimate",
        "calibrated_share": round(220 / 320, 4),
    }
    # original = forwarded + saved per request: 1870 (calibrated) + 400 + 900 (estimate)
    assert tokens["original"] == {
        "value": 3170,
        "method": "estimate",
        "calibrated_share": round(1870 / 3170, 4),
    }
    assert tokens["saving_pct"] == {"value": round(100 * 320 / 3170, 2), "method": "estimate"}


def test_summary_labels_mixed_totals_as_estimate_with_share(query: MetricsQuery) -> None:
    """A total is calibrated only when every request in it is (TC-015)."""
    only_calibrated = query.summary(filters(**{"to": "2026-10-01T10:30:00Z"}))
    assert only_calibrated["tokens"]["saved"] == {"value": 220, "method": "calibrated"}
    assert only_calibrated["tokens"]["forwarded"] == {"value": 1650, "method": "exact"}
    assert only_calibrated["tokens"]["original"] == {"value": 1870, "method": "calibrated"}


def test_summary_compressor_filter(query: MetricsQuery) -> None:
    """API-010: the saving is that compressor's; the requests are those where it was considered."""
    by_id = query.summary(filters(compressor="fake_b"))
    assert by_id["requests"]["total"] == 1
    assert by_id["tokens"]["saved"] == {"value": 55, "method": "calibrated"}
    assert by_id["tokens"]["forwarded"] == {"value": 1650, "method": "exact"}
    assert query.summary(filters(kind="LOSSY"))["tokens"]["saved"]["value"] == 55
    lossless = query.summary(filters(kind="LOSSLESS"))
    assert lossless["requests"]["total"] == 3
    assert lossless["tokens"]["saved"]["value"] == 165 + 100 + 0


def test_summary_cost_block_null_until_s6(query: MetricsQuery) -> None:
    assert query.summary(filters())["cost"] == {"value": None, "reason": "no_price_book"}


def test_summary_empty_database(tmp_path: Path) -> None:
    """API-011: no data is not an error."""
    write(tmp_path / "t.db", [])
    result = MetricsQuery(tmp_path / "t.db").summary(filters())
    assert result["requests"] == {"total": 0, "measured": 0, "by_outcome": {}}
    for name in ("original", "forwarded", "saved", "saving_pct"):
        assert result["tokens"][name] == {"value": None, "reason": "no_data"}


def test_summary_missing_database_file(tmp_path: Path) -> None:
    result = MetricsQuery(tmp_path / "absent.db").summary(filters())
    assert result["requests"]["total"] == 0


def test_compressor_aggregates_hand_computed(query: MetricsQuery) -> None:
    """AC-TC-12 / TC-016."""
    rows = {row["compressor_id"]: row for row in query.compressors(filters())["compressors"]}
    jm = rows["json_minify"]
    assert (jm["considered"], jm["applicable"], jm["accepted"]) == (10, 6, 3)
    assert jm["tokens_in"] == {"value": 1400, "method": "estimate"}
    assert jm["marginal_saved"] == {
        "value": 265,
        "method": "estimate",
        "calibrated_share": round(165 / 265, 4),
    }
    assert jm["zero_benefit_rate"] == {"value": 0.5}
    assert jm["failure_rate"] == {"value": round(1 / 6, 4)}
    assert jm["share_of_saving"] == {"value": round(265 / 320, 4)}
    assert jm["avg_saving_pct_per_accepted"] == {"value": round(100 * 250 / 850, 2)}
    assert jm["ms_total"] == 3.0 and jm["avg_ms"] == {"value": 0.5}
    assert jm["tokens_saved_per_ms"] == {"value": round(250 / 3.0, 2), "method": "estimate"}
    assert jm["latency_without_benefit"] is False
    fake = rows["fake_b"]
    assert fake["kind"] == "LOSSY" and fake["marginal_saved"] == {
        "value": 55,
        "method": "calibrated",
    }


def test_compressor_rates_without_applicable_are_null(tmp_path: Path) -> None:
    record = replace(BASE, request_id="01TEST0000000000000000000Z")
    write(tmp_path / "t.db", [(record, [stats(record.request_id, applicable=0, accepted=0)])])
    row = MetricsQuery(tmp_path / "t.db").compressors(filters())["compressors"][0]
    for name in ("zero_benefit_rate", "failure_rate", "avg_ms"):
        assert row[name] == {"value": None, "reason": "no_applicable_invocations"}


def test_latency_without_benefit_flag(tmp_path: Path) -> None:
    """TC-016: ≥ 90 % zero-benefit, ≥ 1 ms average, ≥ 100 applicable."""

    def db(applicable: int, accepted: int, ms_total: float) -> dict[str, Any]:
        path = tmp_path / f"{applicable}-{accepted}-{ms_total}.db"
        record = replace(BASE, request_id="01TEST0000000000000000000F")
        write(
            path,
            [
                (
                    record,
                    [
                        stats(
                            record.request_id,
                            considered=applicable,
                            applicable=applicable,
                            accepted=accepted,
                            ms_total=ms_total,
                        )
                    ],
                )
            ],
        )
        return MetricsQuery(path).compressors(filters())["compressors"][0]

    assert db(100, 5, 150.0)["latency_without_benefit"] is True
    assert db(99, 5, 150.0)["latency_without_benefit"] is False  # too few invocations
    assert db(100, 11, 150.0)["latency_without_benefit"] is False  # 89 % zero-benefit
    assert db(100, 5, 99.0)["latency_without_benefit"] is False  # 0.99 ms average


def test_overhead_percentiles_by_bucket(tmp_path: Path) -> None:
    """AC-TC-7: 300 records, 75 per bucket with overheads 1…75 ms (nearest-rank)."""
    sizes = {"lt_10k": 5_000, "10k_50k": 20_000, "50k_200k": 100_000, "gt_200k": 300_000}
    items = []
    n = 0
    for size in sizes.values():
        for ms in range(1, 76):
            n += 1
            items.append(
                (
                    replace(
                        BASE,
                        request_id=f"01TEST{n:020d}",
                        est_request_tokens_original=size,
                        ms_tokli_overhead=float(ms),
                    ),
                    [],
                )
            )
    write(tmp_path / "t.db", items)
    overhead = MetricsQuery(tmp_path / "t.db").summary(filters())["overhead"]
    assert overhead["target"] == {"value": 25.0, "unit": "ms", "kind": "target"}
    [group] = overhead["groups"]
    assert (group["policy"], group["config_hash"]) == ("LOSSLESS_ONLY", "hash-a")
    for name in sizes:
        assert group["buckets"][name] == {
            "n": 75,
            "p50": 38.0,
            "p95": 72.0,
            "p99": 75.0,
            "max": 75.0,
        }
    assert group["buckets"]["unknown"]["n"] == 0


def test_target_is_reference_not_status(query: MetricsQuery) -> None:
    text = json.dumps(query.summary(filters())["overhead"])
    assert '"status"' not in text and "pass" not in text and "fail" not in text


def test_unknown_size_bucket(query: MetricsQuery) -> None:
    """TC-013: rows without a whole-request estimate go to `unknown`, never into a size bucket."""
    [group] = query.summary(filters())["overhead"]["groups"]
    assert group["buckets"]["unknown"]["n"] == 2  # the verbatim route and the 429
    assert group["buckets"]["lt_10k"]["n"] == 3


def test_overhead_groups_by_policy_and_config_hash(tmp_path: Path) -> None:
    items = [
        (replace(BASE, request_id="01TEST0000000000000000000G", config_hash="h1"), []),
        (replace(BASE, request_id="01TEST0000000000000000000H", config_hash="h2"), []),
    ]
    write(tmp_path / "t.db", items)
    groups = MetricsQuery(tmp_path / "t.db").summary(filters())["overhead"]["groups"]
    assert [g["config_hash"] for g in groups] == ["h1", "h2"]


def test_timeseries_hour_and_day_buckets(query: MetricsQuery) -> None:
    hourly = query.timeseries(filters(bucket="hour"))
    assert len(hourly["buckets"]) == 24
    by_start = {b["start"]: b for b in hourly["buckets"]}
    assert by_start["2026-10-01T10:00:00+00:00"]["requests"] == 1
    assert by_start["2026-10-01T10:00:00+00:00"]["saved"] == {"value": 220, "method": "calibrated"}
    assert by_start["2026-10-01T09:00:00+00:00"]["saved"] == {"value": None, "reason": "no_data"}
    daily = query.timeseries(filters(bucket="day"))
    assert [b["start"] for b in daily["buckets"]] == ["2026-10-01T00:00:00+00:00"]
    assert daily["buckets"][0]["requests"] == 5


def test_timeseries_buckets_follow_tz_across_dst(tmp_path: Path) -> None:
    """AC-API-7: Rome leaves summer time on 2026-10-25, New York on 2026-11-01."""
    times = [
        ("01TEST0000000000000000000J", "2026-10-24T22:30:00.000+00:00"),  # 00:30 on the 25th (CEST)
        ("01TEST0000000000000000000K", "2026-10-25T22:30:00.000+00:00"),  # 23:30 on the 25th (CET)
        ("01TEST0000000000000000000L", "2026-10-25T23:30:00.000+00:00"),  # 00:30 on the 26th (CET)
    ]
    write(tmp_path / "t.db", [(replace(BASE, request_id=r, ts_start=t), []) for r, t in times])
    rome = MetricsQuery(tmp_path / "t.db").timeseries(
        parse_filters(
            {
                "from": "2026-10-24T22:00:00Z",
                "to": "2026-10-26T23:00:00Z",
                "tz": "Europe/Rome",
                "bucket": "day",
            }
        )
    )
    assert [(b["start"], b["requests"]) for b in rome["buckets"]] == [
        ("2026-10-25T00:00:00+02:00", 2),
        ("2026-10-26T00:00:00+01:00", 1),
    ]
    new_york = MetricsQuery(tmp_path / "t.db").timeseries(
        parse_filters(
            {
                "from": "2026-10-31T04:00:00Z",
                "to": "2026-11-02T05:00:00Z",
                "tz": "America/New_York",
                "bucket": "day",
            }
        )
    )
    assert [b["start"] for b in new_york["buckets"]] == [
        "2026-10-31T00:00:00-04:00",
        "2026-11-01T00:00:00-04:00",
    ]


def test_requests_list_newest_first_and_paged(tmp_path: Path) -> None:
    items = [
        (
            replace(
                BASE,
                request_id=f"01TEST00000000000000000{i:03d}",
                ts_start=f"2026-10-01T10:{i:02d}:00.000+00:00",
            ),
            [],
        )
        for i in range(7)
    ]
    write(tmp_path / "t.db", items)
    query = MetricsQuery(tmp_path / "t.db")
    first = query.requests(limit=3, cursor=None)
    assert [r["request_id"][-3:] for r in first["requests"]] == ["006", "005", "004"]
    second = query.requests(limit=3, cursor=first["next_cursor"])
    assert [r["request_id"][-3:] for r in second["requests"]] == ["003", "002", "001"]
    last = query.requests(limit=3, cursor=second["next_cursor"])
    assert [r["request_id"][-3:] for r in last["requests"]] == ["000"]
    assert last["next_cursor"] is None


def test_requests_list_metadata_only(query: MetricsQuery) -> None:
    item = query.requests(limit=10, cursor=None)["requests"][-1]
    assert item["request_id"] == "01TEST0000000000000000000A"
    assert item["tokens"]["saved"] == {"value": 220, "method": "calibrated"}
    assert item["tokens"]["forwarded"] == {"value": 1650, "method": "exact"}
    assert set(item) == {
        "request_id",
        "ts_start",
        "provider",
        "model",
        "stream",
        "outcome",
        "reason",
        "status_code",
        "usage_source",
        "overhead_ms",
        "tokens",
    }


@pytest.mark.parametrize(
    "params, field",
    [
        ({"from": "yesterday"}, "from"),
        ({"to": "2026-13-01T00:00:00Z"}, "to"),
        ({"from": "2026-10-01T00:00:00"}, "from"),  # no offset
        ({"from": "2026-10-02T00:00:00Z", "to": "2026-10-01T00:00:00Z"}, "to"),
        ({"tz": "Mars/Olympus"}, "tz"),
        ({"bucket": "week"}, "bucket"),
        ({"kind": "FAST"}, "kind"),
        ({"limit": "0"}, "limit"),
        ({"limit": "501"}, "limit"),
        ({"cursor": "not-a-ulid"}, "cursor"),
    ],
)
def test_metrics_filters_validated(params: dict[str, str], field: str) -> None:
    """API-003 / API-010."""
    with pytest.raises(InvalidParameters) as info:
        parse_filters(params)
    assert field in info.value.fields


def test_filters_default_to_last_seven_days() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    parsed = parse_filters({}, now=now)
    assert parsed.end == now and (now - parsed.start).days == 7
    assert parsed.tz.key == "UTC"
