"""SPEC 013 TC-004, TC-017 end to end: a compressed request through the proxy records where its
saving sits among the usage regions, and the summary prices it by position."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from tests.integration.servers import FakeUpstream, Tokli

HEADERS = {
    "x-api-key": "sk-ant-api03-TOKLI-CANARY",
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}
Start = Callable[..., Tokli]
LISTING = json.dumps(
    [{"id": n, "name": f"synthetic-item-{n}", "tags": ["alpha", "beta"]} for n in range(60)],
    indent=2,
)


def conversation() -> dict[str, Any]:
    """An early JSON tool result (compressible) followed by later turns: the saving sits in the
    cached prefix."""
    return {
        "model": "claude-sonnet-5",
        "max_tokens": 16,
        "messages": [
            {"role": "user", "content": "List the synthetic items."},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_01", "name": "mcp__api__list", "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_01", "content": LISTING}],
            },
            {"role": "assistant", "content": "There are sixty synthetic items. " * 40},
            {"role": "user", "content": "Which one comes first? " * 40},
        ],
    }


def cached_upstream(upstream: FakeUpstream, read_share: float) -> None:
    """Usage in byte units (the test tokenizer counts bytes): the first ``read_share`` of the
    forwarded request was read from cache, the rest written to it."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

    async def responder(request: Request) -> Response:
        size = len(await request.body())
        read = int(size * read_share)
        usage = {
            "input_tokens": 0,
            "cache_read_input_tokens": read,
            "cache_creation_input_tokens": size - read,
            "output_tokens": 3,
        }
        return JSONResponse({"type": "message", "content": [], "usage": usage})

    upstream.responder = responder


def send(t: Tokli) -> str:
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=json.dumps(conversation()).encode(),
        headers=HEADERS,
        timeout=10,
    )
    assert response.status_code == 200
    rid = response.headers["x-tokli-request-id"]
    t.wait_trace(rid)
    assert t.services.store is not None
    t.services.store.flush()
    return rid


def test_saving_regions_recorded_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """TC-017: the JSON result sits in the first half of the request; with 80 % read from cache
    its whole saving is in the cache-read region, for the request and for its compressor."""
    cached_upstream(upstream, 0.8)
    t = tokli()
    stored = t.services.store.get(send(t))  # type: ignore[union-attr]
    assert stored is not None
    record = stored["record"]
    saving = record["est_original_tokens"] - record["est_forwarded_tokens"]
    assert saving > 0
    assert (record["saved_cache_read"], record["saved_cache_write"], record["saved_input"]) == (
        saving,
        0,
        0,
    )
    minify = next(c for c in stored["compressors"] if c["compressor_id"] == "json_minify")
    assert (minify["saved_cache_read"], minify["saved_cache_write"]) == (saving, 0)


def test_saving_in_written_region_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """On a first request nothing is read from cache: the saving sits in the written region."""
    cached_upstream(upstream, 0.0)
    t = tokli()
    record = t.services.store.get(send(t))["record"]  # type: ignore[union-attr]
    saving = record["est_original_tokens"] - record["est_forwarded_tokens"]
    assert (record["saved_cache_read"], record["saved_cache_write"]) == (0, saving)


def test_summary_prices_by_position_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """TC-004: priced at the shipped `claude-sonnet-5` cache-read price, method positional."""
    cached_upstream(upstream, 0.8)
    t = tokli()
    record = t.services.store.get(send(t))["record"]  # type: ignore[union-attr]
    cost = httpx.get(t.url + "/tokli/api/metrics/summary", timeout=10).json()["cost"]
    saved = cost["saved"]
    assert saved["method"] == "positional" and saved["basis"] == "billed"
    calibrated = round(
        (record["est_original_tokens"] - record["est_forwarded_tokens"]) * record["calibration_k"]
    )
    assert abs(saved["estimate"] - calibrated * 0.20 / 1_000_000) < 1e-8
    assert cost["priced_requests"] == 1


USER_BOOK = """
version: mine-1
currency: USD
source_note: a synthetic negotiated price
models:
  - match: claude-sonnet-5
    provider: anthropic
    effective_from: 2026-01-01
    per_mtok: {input: 1, cache_write_5m: 1.25, cache_write_1h: 2, cache_read: 0.1, output: 5}
"""


def test_user_price_book_used_at_startup(tmp_path: Any, upstream: FakeUpstream) -> None:
    """TC-018: `<data>/price-book.yaml` takes precedence for the models it matches."""
    from datetime import UTC, datetime

    from tests.integration.servers import BYTE_CATALOG, make_config
    from tokli.app.bootstrap import bootstrap

    config = make_config(tmp_path, upstream.url)
    (config.dirs.data_dir / "price-book.yaml").write_text(USER_BOOK, encoding="utf-8")
    services = bootstrap(config, catalog=BYTE_CATALOG, version="test", telemetry=False)
    now = datetime.now(UTC)
    mine = services.prices.lookup("claude-sonnet-5", now)
    shipped = services.prices.lookup("claude-opus-5-5", now)
    assert mine is not None and mine.version == "mine-1"
    assert shipped is not None and shipped.version != "mine-1"


def test_invalid_user_price_book_stops_startup(tmp_path: Any, upstream: FakeUpstream) -> None:
    """AC-TC-14: an invalid user price book is a startup error naming the file and the problem."""
    import pytest

    from tests.integration.servers import BYTE_CATALOG, make_config
    from tokli.app.bootstrap import StartupError, bootstrap

    config = make_config(tmp_path, upstream.url)
    path = config.dirs.data_dir / "price-book.yaml"
    path.write_text("version: x\ncurrency: EUR\nsource_note: s\nmodels: []\n", encoding="utf-8")
    with pytest.raises(StartupError) as info:
        bootstrap(config, catalog=BYTE_CATALOG, version="test", telemetry=False)
    assert str(path) in info.value.cause and "currency" in info.value.cause
