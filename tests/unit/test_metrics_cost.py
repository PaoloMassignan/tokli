"""SPEC 013 TC-004…TC-006, TC-019, TC-020 and SPEC 015 API-002, API-013: the money figures of
the metrics use cases, on a real SQLite store with hand-built records (values by hand)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from tests.unit.test_metrics import BASE, WINDOW, stats, write
from tests.unit.test_pricing import BOOK
from tokli.app.metrics import MetricsQuery, parse_filters
from tokli.pricing.book import PriceTable, parse_price_book

USAGE = {
    "usage_source": "provider",
    "usage_input": 1000,
    "usage_cache_read": 80000,
    "usage_cache_write_5m": 5000,
    "usage_cache_write_1h": 0,
    "usage_output": 200,
}
# r1: positional (split 3000 / 500 / 100 of a 3,600 saving), k 1.0
R1 = replace(
    BASE,
    request_id="01COST0000000000000000000A",
    model="claude-test-1",
    outcome="compressed",
    est_original_tokens=5000,
    est_forwarded_tokens=1400,
    calibration_k=1.0,
    est_request_tokens_original=89600,
    est_request_tokens_forwarded=86000,
    saved_cache_read=3000,
    saved_cache_write=500,
    saved_input=100,
    **USAGE,
)
# r2: no split → proportional
R2 = replace(
    R1,
    request_id="01COST0000000000000000000B",
    ts_start="2026-10-01T11:00:00.000+00:00",
    saved_cache_read=None,
    saved_cache_write=None,
    saved_input=None,
    config_hash="hash-b",
    history_rewritten=True,
)
# r3: a model without a price
R3 = replace(R1, request_id="01COST0000000000000000000C", model="gpt-unknown")
M = Decimal(1_000_000)
FORWARDED = Decimal("0.0325")
POSITIONAL = Decimal("0.00205")
PROPORTIONAL = Decimal(3600) * Decimal(30500) / Decimal(86000) / M


def query_for(tmp_path: Path, items: list[Any]) -> MetricsQuery:
    write(tmp_path / "t.db", items)
    return MetricsQuery(tmp_path / "t.db", prices=PriceTable(parse_price_book(BOOK)))


def money(value: Decimal) -> float:
    return float(round(value, 8))


def test_summary_cost_block_hand_computed(tmp_path: Path) -> None:
    """API-013: sums over the priced requests; the weakest method with the shares."""
    split_stats = stats(R1.request_id, marginal_saved=3600)
    q = query_for(tmp_path, [(R1, [split_stats]), (R2, []), (R3, [])])
    cost = q.summary(parse_filters(WINDOW))["cost"]
    assert cost["priced_requests"] == 2 and cost["unpriced_requests"] == 1
    saved = cost["saved"]
    assert saved["estimate"] == money(POSITIONAL + PROPORTIONAL)
    assert saved["low"] == money(Decimal(2 * 3600) * Decimal("0.2") / M)
    assert saved["high"] == money(Decimal(2 * 3600) * Decimal("2.5") / M)
    assert saved["method"] == "proportional"
    assert saved["method_shares"] == {
        "positional": round(float(POSITIONAL / (POSITIONAL + PROPORTIONAL)), 4),
        "proportional": round(float(PROPORTIONAL / (POSITIONAL + PROPORTIONAL)), 4),
    }
    assert saved["currency"] == "USD" and saved["price_book_version"] == "test-1"
    assert saved["basis"] == "billed"
    assert cost["forwarded"]["estimate"] == money(2 * FORWARDED)
    assert cost["original"]["estimate"] == money(2 * FORWARDED + POSITIONAL + PROPORTIONAL)


def test_cost_caveats_hand_computed(tmp_path: Path) -> None:
    """AC-TC-16: one request rewrote history; the config hash changed a → b → a: 2 changes."""
    r4 = replace(
        R1, request_id="01COST0000000000000000000D", ts_start="2026-10-01T12:00:00.000+00:00"
    )
    q = query_for(tmp_path, [(R1, []), (R2, []), (r4, [])])
    caveats = q.summary(parse_filters(WINDOW))["cost"]["caveats"]
    assert caveats == {"history_rewritten_requests": 1, "config_changes": 2}


def test_oauth_cost_basis_api_equivalent(tmp_path: Path) -> None:
    """AC-TC-15: one OAuth request makes the total a value at API prices."""
    oauth = replace(R2, credential_kind="oauth")
    assert (
        query_for(tmp_path / "a", [(R1, [])]).summary(parse_filters(WINDOW))["cost"]["saved"][
            "basis"
        ]
        == "billed"
    )
    cost = query_for(tmp_path / "b", [(R1, []), (oauth, [])]).summary(parse_filters(WINDOW))["cost"]
    assert cost["saved"]["basis"] == "api_equivalent"


def test_cost_unavailable_without_price_keeps_tokens(tmp_path: Path) -> None:
    """AC-TC-4: no priced request → null money with the reason; tokens are still reported."""
    q = query_for(tmp_path, [(R3, [])])
    summary = q.summary(parse_filters(WINDOW))
    assert summary["cost"]["saved"] == {"value": None, "reason": "no_price_for_model"}
    assert summary["tokens"]["saved"]["value"] == 3600


def test_cost_empty_range(tmp_path: Path) -> None:
    q = query_for(tmp_path, [])
    assert q.summary(parse_filters(WINDOW))["cost"]["saved"] == {"value": None, "reason": "no_data"}


def test_cost_without_price_book(tmp_path: Path) -> None:
    write(tmp_path / "t.db", [(R1, [])])
    cost = MetricsQuery(tmp_path / "t.db").summary(parse_filters(WINDOW))["cost"]
    assert cost["saved"] == {"value": None, "reason": "no_price_book"}


def test_cost_assumes_uncached_without_usage(tmp_path: Path) -> None:
    """TC-006: a compressed request without usage: saving at the input price, no forwarded cost."""
    no_usage = replace(
        R1,
        usage_source="unavailable",
        usage_input=None,
        usage_cache_read=None,
        usage_cache_write_5m=None,
        usage_cache_write_1h=None,
        usage_output=None,
        calibration_k=None,
        saved_cache_read=None,
        saved_cache_write=None,
        saved_input=None,
    )
    cost = query_for(tmp_path, [(no_usage, [])]).summary(parse_filters(WINDOW))["cost"]
    assert cost["saved"]["method"] == "assumes_uncached"
    assert cost["saved"]["estimate"] == money(Decimal(3600) * 2 / M)
    assert cost["forwarded"] == {"value": None, "reason": "usage_unavailable"}


def test_compressor_money_saved(tmp_path: Path) -> None:
    """API-013 (P2): per compressor, from its own split."""
    rows = [
        stats(
            R1.request_id,
            marginal_saved=3000,
            saved_cache_read=3000,
            saved_cache_write=0,
            saved_input=0,
        ),
        stats(
            R1.request_id,
            cid="reread_by_reference",
            marginal_saved=600,
            saved_cache_read=0,
            saved_cache_write=500,
            saved_input=100,
        ),
    ]
    q = query_for(tmp_path, [(R1, rows)])
    by_id = {c["compressor_id"]: c for c in q.compressors(parse_filters(WINDOW))["compressors"]}
    assert by_id["json_minify"]["money_saved"]["estimate"] == money(
        Decimal(3000) * Decimal("0.2") / M
    )
    assert by_id["reread_by_reference"]["money_saved"]["estimate"] == money(
        (Decimal(500) * Decimal("2.5") + Decimal(100) * 2) / M
    )
    assert by_id["json_minify"]["money_saved"]["method"] == "positional"


def test_requests_list_carries_money(tmp_path: Path) -> None:
    q = query_for(tmp_path, [(R1, []), (R3, [])])
    items = {item["request_id"]: item for item in q.requests(10, None)["requests"]}
    assert items[R1.request_id]["cost"]["saved"]["estimate"] == money(POSITIONAL)
    assert items[R3.request_id]["cost"]["saved"] == {"value": None, "reason": "no_price_for_model"}


@pytest.mark.parametrize("field", ["saved_cache_read", "saved_cache_write", "saved_input"])
def test_split_scaled_by_calibrated_saving(tmp_path: Path, field: str) -> None:
    """The split is in estimate units; it is scaled to the calibrated saving (k 1.5 → x1.5)."""
    split = {"saved_cache_read": 0, "saved_cache_write": 0, "saved_input": 0, field: 3600}
    record = replace(R1, calibration_k=1.5, **split)
    cost = query_for(tmp_path, [(record, [])]).summary(parse_filters(WINDOW))["cost"]
    price = {"saved_cache_read": "0.2", "saved_cache_write": "2.5", "saved_input": "2"}[field]
    assert cost["saved"]["estimate"] == money(Decimal(5400) * Decimal(price) / M)
