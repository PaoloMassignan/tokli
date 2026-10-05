"""SPEC 013 TC-004…TC-008, TC-018: the price book and the money arithmetic (values by hand)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tokli.pricing.book import PriceBookError, PriceTable, load_shipped, parse_price_book
from tokli.pricing.cost import UsageTokens, forwarded_cost, saving_cost

AT = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
BOOK = """
version: test-1
currency: USD
source_note: synthetic prices for tests
models:
  - match: ["claude-test-*"]
    provider: anthropic
    effective_from: 2026-01-01
    per_mtok: {input: 2, cache_write_5m: 2.5, cache_write_1h: 4, cache_read: 0.2, output: 10}
  - match: ["claude-test-big*"]
    provider: anthropic
    effective_from: 2026-01-01
    per_mtok: {input: 4, cache_write_5m: 5, cache_write_1h: 8, cache_read: 0.4, output: 20}
  - match: ["claude-test-*"]
    provider: anthropic
    effective_from: 2026-11-01
    per_mtok: {input: 3, cache_write_5m: 3.75, cache_write_1h: 6, cache_read: 0.3, output: 15}
"""
# input 1,000 · cache read 80,000 · 5-minute write 5,000 · output 200
USAGE = UsageTokens(input=1000, cache_read=80000, cache_write_5m=5000, cache_write_1h=0, output=200)


def prices():  # type: ignore[no-untyped-def]
    match = PriceTable(parse_price_book(BOOK)).lookup("claude-test-1", AT)
    assert match is not None
    return match.prices


def test_forwarded_cost_hand_computed() -> None:
    """TC-004: (1000x2 + 80000x0.2 + 5000x2.5 + 200x10) / 1e6 = 0.0325."""
    assert forwarded_cost(prices(), USAGE) == Decimal("0.0325")


def test_cost_positional_estimate_and_bounds() -> None:
    """AC-TC-3: 3,000 saved in the cached prefix, 500 in the written part, 100 uncached:
    (3000x0.2 + 500x2.5 + 100x2) / 1e6 = 0.00205; bounds at 0.2 and 2.5 per MTok."""
    money = saving_cost(prices(), Decimal(3600), USAGE, (Decimal(3000), Decimal(500), Decimal(100)))
    assert money.method == "positional"
    assert money.estimate == Decimal("0.00205")
    assert (money.low, money.high) == (Decimal("0.00072"), Decimal("0.009"))


def test_cost_proportional_without_split() -> None:
    """AC-TC-3: no split → the input-side mix: 3600 x 30500 / 86000 / 1e6."""
    money = saving_cost(prices(), Decimal(3600), USAGE, None)
    assert money.method == "proportional"
    assert money.estimate == Decimal(3600) * Decimal(30500) / Decimal(86000) / Decimal(1_000_000)
    assert (money.low, money.high) == (Decimal("0.00072"), Decimal("0.009"))


def test_cost_mixed_cache_writes_priced_at_their_mix() -> None:
    """TC-004: a write region with 5-minute and 1-hour tokens is priced at their mix."""
    usage = UsageTokens(input=0, cache_read=0, cache_write_5m=3000, cache_write_1h=1000, output=0)
    money = saving_cost(prices(), Decimal(400), usage, (Decimal(0), Decimal(400), Decimal(0)))
    # write price = (3000x2.5 + 1000x4) / 4000 = 2.875 per MTok
    assert money.estimate == Decimal(400) * Decimal("2.875") / Decimal(1_000_000)
    assert (money.low, money.high) == (Decimal("0.001"), Decimal("0.0016"))


def test_cost_assumes_uncached_without_usage() -> None:
    """TC-006: without usage the saving is priced at the input price; the low bound is the cache
    read price, the high bound the most expensive input-side price."""
    money = saving_cost(prices(), Decimal(3600), None, None)
    assert money.method == "assumes_uncached"
    assert money.estimate == Decimal("0.0072")
    assert (money.low, money.high) == (Decimal("0.00072"), Decimal("0.0144"))


def test_no_output_savings_claimed() -> None:
    """TC-007: the output price never enters the saving, whatever the output usage."""
    more_output = UsageTokens(
        input=1000, cache_read=80000, cache_write_5m=5000, cache_write_1h=0, output=999_999
    )
    split = (Decimal(3000), Decimal(500), Decimal(100))
    assert saving_cost(prices(), Decimal(3600), more_output, split) == saving_cost(
        prices(), Decimal(3600), USAGE, split
    )


def test_cost_unavailable_without_price() -> None:
    """TC-005: a model without an entry has no price."""
    assert PriceTable(parse_price_book(BOOK)).lookup("gpt-unknown", AT) is None
    assert PriceTable(parse_price_book(BOOK)).lookup(None, AT) is None


def test_price_match_most_specific() -> None:
    """TC-008: the most specific pattern wins (fewest `*`, then the longest literal)."""
    table = PriceTable(parse_price_book(BOOK))
    big = table.lookup("claude-test-big-1", AT)
    assert big is not None and big.prices.input == Decimal(4)
    small = table.lookup("claude-test-1", AT)
    assert small is not None and small.prices.input == Decimal(2)


def test_price_effective_dates() -> None:
    """AC-TC-5: a later entry does not change the price of earlier requests."""
    table = PriceTable(parse_price_book(BOOK))
    before = table.lookup("claude-test-1", AT)
    after = table.lookup("claude-test-1", datetime(2026, 11, 2, tzinfo=UTC))
    assert before is not None and before.prices.input == Decimal(2)
    assert after is not None and after.prices.input == Decimal(3)
    assert table.lookup("claude-test-1", datetime(2025, 12, 31, tzinfo=UTC)) is None


def test_user_price_book_overrides_shipped() -> None:
    """AC-TC-14: a user entry takes precedence for the models it matches, and only for those."""
    user = parse_price_book(
        """
version: mine-1
currency: USD
source_note: my negotiated price
models:
  - match: claude-test-1
    provider: anthropic
    effective_from: 2026-01-01
    per_mtok: {input: 1, cache_write_5m: 1.25, cache_write_1h: 2, cache_read: 0.1, output: 5}
"""
    )
    table = PriceTable(parse_price_book(BOOK), user)
    mine = table.lookup("claude-test-1", AT)
    other = table.lookup("claude-test-2", AT)
    assert mine is not None and mine.prices.input == Decimal(1) and mine.version == "mine-1"
    assert other is not None and other.prices.input == Decimal(2) and other.version == "test-1"


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("version: x\ncurrency: USD\nsource_note: s\nmodels: []\n", "models"),
        ("version: x\ncurrency: EUR\nsource_note: s\nmodels: []\n", "currency"),
        (
            "version: x\ncurrency: USD\nsource_note: s\nmodels:\n"
            "  - match: a*\n    provider: anthropic\n    effective_from: 2026-01-01\n"
            "    per_mtok: {input: 1}\n",
            "per_mtok",
        ),
        (
            "version: x\ncurrency: USD\nsource_note: s\nmodels:\n"
            "  - match: a*\n    provider: anthropic\n    effective_from: 2026-01-01\n"
            "    per_mtok: {input: -1, cache_write_5m: 1, cache_write_1h: 1, cache_read: 1,"
            " output: 1}\n",
            "input",
        ),
        ("version: [\n", "YAML"),
    ],
)
def test_invalid_price_book_is_rejected(text: str, problem: str) -> None:
    with pytest.raises(PriceBookError) as info:
        parse_price_book(text)
    assert problem in str(info.value)


def test_shipped_price_book_is_dated_and_sourced() -> None:
    """TC-008, TC-018: every shipped entry has a date; the book names its source and covers the
    current Anthropic models at the prices of the official page (read 2026-10-04)."""
    book = load_shipped()
    assert book.currency == "USD" and "platform.claude.com" in book.source_note
    assert all(isinstance(entry.effective_from, date) for entry in book.entries)
    table = PriceTable(book)
    expected = {
        # model: (input, 5m write, 1h write, cache read, output) per MTok
        "claude-opus-5-5": ("4", "5", "8", "0.20", "20"),
        "claude-sonnet-5": ("2", "2.50", "4", "0.20", "10"),
        "claude-haiku-4-5-20251001": ("1", "1.25", "2", "0.10", "5"),
        "claude-fable-5-1": ("10", "12.50", "20", "0.25", "50"),
        "claude-opus-5": ("5", "6.25", "10", "0.50", "25"),
        "claude-sonnet-4-5-20250929": ("3", "3.75", "6", "0.30", "15"),
    }
    for model, values in expected.items():
        match = table.lookup(model, AT)
        assert match is not None, model
        p = match.prices
        got = (p.input, p.cache_write_5m, p.cache_write_1h, p.cache_read, p.output)
        assert got == tuple(Decimal(v) for v in values), model
