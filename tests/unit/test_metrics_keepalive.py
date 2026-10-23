"""SPEC 013 TC-023…TC-025 and S8l SCR-001 (TC-013, TC-015): the keepalive block of the metrics
summary, and keepalive rows left out of every other figure, on a real SQLite store with
hand-built records (values by hand, AC-TC-20)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from tests.unit.test_metrics import BASE, WINDOW, mixed_traffic, write
from tokli.app.metrics import MetricsQuery, parse_filters
from tokli.pricing.book import PriceTable, load_shipped

M = Decimal(1_000_000)
MODEL = "claude-opus-5-5"  # shipped prices per MTok: input 4, write 1 h 8, read 0.20, output 20
PING = replace(
    BASE,
    request_id="01KEEP0000000000000000000A",
    ts_start="2026-10-01T11:00:00.000+00:00",
    model=MODEL,
    stream=False,
    outcome="keepalive",
    segments_total=0,
    segments_mutable=0,
    tokenizer_id=None,
    ms_parse=None,
    ms_pipeline=None,
    ms_tokli_overhead=None,
    ms_total=None,
    usage_source="provider",
    usage_input=4,
    usage_cache_read=60_000,
    usage_cache_write_5m=0,
    usage_cache_write_1h=0,
    usage_output=1,
    stop_reason="max_tokens",
)
PINGS = [
    PING,
    replace(
        PING, request_id="01KEEP0000000000000000000B", ts_start="2026-10-01T11:55:00.000+00:00"
    ),
    replace(
        PING,
        request_id="01KEEP0000000000000000000C",
        ts_start="2026-10-01T12:50:00.000+00:00",
        keepalive_stop_reason="horizon",
    ),
]
BRIDGED = replace(
    BASE,
    request_id="01KEEP0000000000000000000D",
    ts_start="2026-10-01T13:00:00.000+00:00",
    model=MODEL,
    usage_source="provider",
    usage_input=4,
    usage_cache_read=60_000,
    usage_cache_write_5m=0,
    usage_cache_write_1h=35,
    usage_output=100,
    est_request_tokens_original=30_000,
    est_request_tokens_forwarded=30_000,
    keepalive_bridged=True,
    cache_ttl_s=3600.0,
)
ORDINARY = replace(BRIDGED, request_id="01KEEP0000000000000000000E", keepalive_bridged=False)
PING_COST = Decimal(3) * (4 * Decimal(4) + 60_000 * Decimal("0.20") + 1 * Decimal(20)) / M
SAVED = Decimal(60_000) * (Decimal(8) - Decimal("0.20")) / M  # $0.468


def query(tmp_path: Path, name: str, items: list[Any]) -> MetricsQuery:
    write(tmp_path / name, items)
    return MetricsQuery(tmp_path / name, prices=PriceTable(load_shipped()))


def usd(value: Decimal) -> float:
    return float(round(value, 8))


def test_keepalive_summary_hand_computed(tmp_path: Path) -> None:
    """AC-TC-20 (TC-024, TC-025): counts, ping cost, saving, net and basis by hand."""
    q = query(tmp_path, "t.db", [(r, []) for r in (*PINGS, BRIDGED, ORDINARY)])
    block = q.summary(parse_filters(WINDOW))["keepalive"]
    assert block["pings"] == 3
    assert block["successful_pings"] == 3
    assert block["bridged_requests"] == 1
    assert block["stop_reasons"] == {"horizon": 1}
    assert Decimal("0.468") == SAVED
    assert block["ping_cost"]["estimate"] == usd(PING_COST)
    assert block["saved"]["estimate"] == usd(SAVED)
    assert block["net"]["estimate"] == usd(SAVED - PING_COST)
    for name in ("ping_cost", "saved", "net"):
        assert block[name]["basis"] == "billed"
        assert block[name]["currency"] == "USD"
    assert block["ping_cost"]["method"] == "provider_usage"  # API-002
    assert block["saved"]["method"] == block["net"]["method"] == "bridged_cache_reads"  # SCR-003


def test_keepalive_saving_at_five_minute_price(tmp_path: Path) -> None:
    """TC-025: a bridged request whose lifetime is five minutes is priced at the 5 min write
    price; an OAuth row makes the basis `api_equivalent` (TC-019)."""
    five = replace(BRIDGED, cache_ttl_s=300.0, credential_kind="oauth")
    q = query(tmp_path, "t.db", [(five, [])])
    block = q.summary(parse_filters(WINDOW))["keepalive"]
    assert block["saved"]["estimate"] == usd(Decimal(60_000) * (Decimal(5) - Decimal("0.20")) / M)
    assert block["saved"]["basis"] == "api_equivalent"


def test_keepalive_without_price(tmp_path: Path) -> None:
    """TC-025, TC-005: without a price the money fields are null with `no_price_for_model`."""
    rows = [replace(PING, model="gpt-unknown"), replace(BRIDGED, model="gpt-unknown")]
    q = query(tmp_path, "t.db", [(r, []) for r in rows])
    block = q.summary(parse_filters(WINDOW))["keepalive"]
    assert block["pings"] == 1 and block["bridged_requests"] == 1
    for name in ("ping_cost", "saved", "net"):
        assert block[name] == {"value": None, "reason": "no_price_for_model"}


def test_keepalive_rows_excluded_from_totals(tmp_path: Path) -> None:
    """AC-TC-20, TC-013 and TC-015 after S8l SCR-001: the summary's token totals, request
    counts, overhead distribution and cost block, the time series and the compressor
    aggregates equal those of the same records without the pings."""
    base = mixed_traffic()
    plain = query(tmp_path, "plain.db", base)
    pinged = query(tmp_path, "pinged.db", [*base, *((p, []) for p in PINGS)])
    filters = parse_filters(WINDOW)
    a, b = plain.summary(filters), pinged.summary(filters)
    for name in ("requests", "tokens", "overhead", "cost"):
        assert a[name] == b[name], name
    assert plain.timeseries(filters)["buckets"] == pinged.timeseries(filters)["buckets"]
    assert plain.compressors(filters)["compressors"] == pinged.compressors(filters)["compressors"]
    assert a["keepalive"]["pings"] == 0 and b["keepalive"]["pings"] == 3
