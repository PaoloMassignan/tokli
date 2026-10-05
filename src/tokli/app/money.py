"""Money figures of the metrics use cases (SPEC 013 TC-004…TC-006, TC-019; SPEC 015 API-002,
API-013).

Telemetry stores tokens; prices are applied here, at query time, per request (ADR 0014). A
request is priced with the entry of its model effective at its start. Its saving is priced by
where it sat in the cache (its stored region split, scaled to the request's best saving figure),
else at its usage mix, else at the uncached input price.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from tokli.pricing.book import CURRENCY, PriceTable
from tokli.pricing.cost import METHODS, Money, UsageTokens, forwarded_cost, saving_cost

FORWARDED_METHOD = "provider_usage"  # the forwarded cost: exact usage x the price book
_RANK = {method: i for i, method in enumerate((FORWARDED_METHOD, *METHODS))}
_DIGITS = 8  # USD decimals in the API

Split = tuple[int, int, int] | None


@dataclass(frozen=True)
class PricedRequest:
    saved: Money
    forwarded: Decimal | None  # None without provider usage
    version: str
    basis: str  # billed | api_equivalent (TC-019)


def usage_tokens(row: Mapping[str, Any]) -> UsageTokens | None:
    if row["usage_input"] is None or row.get("usage_source") == "unavailable":
        return None
    return UsageTokens(
        input=int(row["usage_input"]),
        cache_read=int(row["usage_cache_read"] or 0),
        cache_write_5m=int(row["usage_cache_write_5m"] or 0),
        cache_write_1h=int(row["usage_cache_write_1h"] or 0),
        output=int(row["usage_output"] or 0),
    )


def split_of(values: Iterable[Mapping[str, Any]]) -> Split:
    """The summed region split of ``values`` (a request row, or stats rows); ``None`` when any
    part is unknown."""
    parts = [0, 0, 0]
    seen = False
    for value in values:
        trio = (value["saved_cache_read"], value["saved_cache_write"], value["saved_input"])
        if any(part is None for part in trio):
            return None
        seen = True
        for i in range(3):
            parts[i] += int(trio[i])
    return (parts[0], parts[1], parts[2]) if seen else None


def price_request(
    prices: PriceTable, row: Mapping[str, Any], saved: int, raw: int, split: Split
) -> PricedRequest | None:
    """``saved``: the request's best saving figure (provider units when calibrated); ``raw``:
    the estimate the split divides. ``None`` when the model has no price (TC-005)."""
    match = prices.lookup(row["model"], datetime.fromisoformat(row["ts_start"]))
    if match is None:
        return None
    usage = usage_tokens(row)
    value = Decimal(saved)
    regions = None
    if usage is not None and split is not None and raw > 0:
        scale = value / Decimal(raw)
        regions = (Decimal(split[0]) * scale, Decimal(split[1]) * scale, Decimal(split[2]) * scale)
    return PricedRequest(
        saved=saving_cost(match.prices, value, usage, regions),
        forwarded=forwarded_cost(match.prices, usage) if usage is not None else None,
        version=match.version,
        basis="api_equivalent" if row.get("credential_kind") == "oauth" else "billed",
    )


def _round(value: Decimal) -> float:
    return float(round(value, _DIGITS))


def _figure(parts: list[tuple[Money, PricedRequest]]) -> dict[str, Any]:
    """A money figure (API-002) summing ``parts``: the weakest method among the parts that
    carry a value, with ``method_shares`` when they differ."""
    estimate = sum((m.estimate for m, _ in parts), Decimal(0))
    contributing = [m for m, _ in parts if m.estimate > 0] or [m for m, _ in parts]
    method = max((m.method for m in contributing), key=_RANK.__getitem__)
    figure: dict[str, Any] = {
        "estimate": _round(estimate),
        "low": _round(sum((m.low for m, _ in parts), Decimal(0))),
        "high": _round(sum((m.high for m, _ in parts), Decimal(0))),
        "method": method,
        "currency": CURRENCY,
        "price_book_version": ", ".join(sorted({p.version for _, p in parts})),
        "basis": (
            "api_equivalent" if any(p.basis == "api_equivalent" for _, p in parts) else "billed"
        ),
    }
    methods = {m.method for m in contributing}
    if len(methods) > 1 and estimate > 0:
        figure["method_shares"] = {
            name: round(
                float(
                    sum((m.estimate for m in contributing if m.method == name), Decimal(0))
                    / estimate
                ),
                4,
            )
            for name in sorted(methods, key=_RANK.__getitem__)
        }
    return figure


def unavailable(reason: str) -> dict[str, Any]:
    return {"value": None, "reason": reason}


def money_block(priced: list[PricedRequest], measured: int) -> dict[str, dict[str, Any]]:
    """Forwarded, saved and original money over the priced requests (API-013). ``measured``
    counts the requests that could have been priced."""
    if not measured:
        return {name: unavailable("no_data") for name in ("forwarded", "saved", "original")}
    if not priced:
        return {
            name: unavailable("no_price_for_model") for name in ("forwarded", "saved", "original")
        }
    saved = _figure([(p.saved, p) for p in priced])
    forwarded: list[tuple[Money, PricedRequest]] = []
    original: list[tuple[Money, PricedRequest]] = []
    for p in priced:
        cost = p.forwarded
        if cost is None:  # without usage there is no forwarded cost, so no original either
            continue
        forwarded.append((Money(cost, cost, cost, FORWARDED_METHOD), p))
        s = p.saved
        original.append((Money(cost + s.estimate, cost + s.low, cost + s.high, s.method), p))
    if not forwarded:
        reason = unavailable("usage_unavailable")
        return {"forwarded": reason, "saved": saved, "original": reason}
    return {"forwarded": _figure(forwarded), "saved": saved, "original": _figure(original)}


def saved_figure(priced: list[PricedRequest], considered: int) -> dict[str, Any]:
    """The money saved alone (per compressor, API-013)."""
    if not considered:
        return unavailable("no_data")
    if not priced:
        return unavailable("no_price_for_model")
    return _figure([(p.saved, p) for p in priced])
