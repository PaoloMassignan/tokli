"""Money from token counts at query time (TC-004…TC-007; TOKLI_TELEMETRY_AND_COST §5).

Only input-side tokens are ever counted as saved (TC-007). A saving is priced by where it sat in
the forwarded request (``positional``), else at the request's input-side mix (``proportional``),
else, without provider usage, at the uncached input price (``assumes_uncached``). Arithmetic is
``decimal``, so every OS gives the same figures.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tokli.pricing.book import Prices

MILLION = Decimal(1_000_000)
METHODS = ("positional", "proportional", "assumes_uncached")  # strongest first


@dataclass(frozen=True)
class UsageTokens:
    input: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    output: int


@dataclass(frozen=True)
class Money:
    estimate: Decimal
    low: Decimal
    high: Decimal
    method: str


def forwarded_cost(prices: Prices, usage: UsageTokens) -> Decimal:
    """What the forwarded request cost: every usage category at its price, output included."""
    return (
        usage.input * prices.input
        + usage.cache_read * prices.cache_read
        + usage.cache_write_5m * prices.cache_write_5m
        + usage.cache_write_1h * prices.cache_write_1h
        + usage.output * prices.output
    ) / MILLION


def _input_side(prices: Prices, usage: UsageTokens) -> list[tuple[int, Decimal]]:
    return [
        (usage.input, prices.input),
        (usage.cache_read, prices.cache_read),
        (usage.cache_write_5m, prices.cache_write_5m),
        (usage.cache_write_1h, prices.cache_write_1h),
    ]


def _write_price(prices: Prices, usage: UsageTokens) -> Decimal:
    """A write region holding 5-minute and 1-hour tokens is priced at their mix (TC-004)."""
    written = usage.cache_write_5m + usage.cache_write_1h
    if not written:
        return prices.cache_write_5m
    return (
        usage.cache_write_5m * prices.cache_write_5m + usage.cache_write_1h * prices.cache_write_1h
    ) / written


def saving_cost(
    prices: Prices,
    saved: Decimal,
    usage: UsageTokens | None,
    regions: tuple[Decimal, Decimal, Decimal] | None,
) -> Money:
    """The money value of ``saved`` provider tokens. ``regions`` splits them into cache read,
    cache write and uncached input (TC-017) and sums to ``saved``."""
    all_prices = (prices.input, prices.cache_read, prices.cache_write_5m, prices.cache_write_1h)
    if usage is None:  # TC-006
        return Money(
            saved * prices.input / MILLION,
            saved * prices.cache_read / MILLION,
            saved * max(all_prices) / MILLION,
            "assumes_uncached",
        )
    present = [price for tokens, price in _input_side(prices, usage) if tokens > 0]
    low_price, high_price = (min(present), max(present)) if present else (prices.input,) * 2
    low, high = saved * low_price / MILLION, saved * high_price / MILLION
    if regions is not None:
        read, write, uncached = regions
        estimate = (
            read * prices.cache_read + write * _write_price(prices, usage) + uncached * prices.input
        ) / MILLION
        return Money(estimate, low, high, "positional")
    total = sum(tokens for tokens, _ in _input_side(prices, usage))
    if not total:
        return Money(saved * prices.input / MILLION, low, high, "proportional")
    weighted = sum(tokens * price for tokens, price in _input_side(prices, usage))
    return Money(saved * weighted / total / MILLION, low, high, "proportional")
