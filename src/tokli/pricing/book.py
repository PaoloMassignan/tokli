"""The price book: dated, sourced prices per model, matched at query time (TC-008, TC-018).

A book is YAML. Each entry names one or more glob patterns on the request's model string, the
date from which it applies, and prices in USD per million tokens. The shipped book comes with
the package; an optional user book in the data directory takes precedence for the models it
matches (ADR 0014).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

CURRENCY = "USD"
USER_FILE = "price-book.yaml"
_PRICE_FIELDS = ("input", "cache_write_5m", "cache_write_1h", "cache_read", "output")


class PriceBookError(ValueError):
    """An invalid price book; the message names the problem."""


@dataclass(frozen=True)
class Prices:
    """USD per million tokens."""

    input: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal
    output: Decimal


@dataclass(frozen=True)
class PriceEntry:
    match: tuple[str, ...]
    provider: str
    effective_from: date
    prices: Prices


@dataclass(frozen=True)
class PriceBook:
    version: str
    currency: str
    source_note: str
    entries: tuple[PriceEntry, ...]


@dataclass(frozen=True)
class Match:
    prices: Prices
    version: str


def _text(node: dict[str, Any], key: str, where: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PriceBookError(f"{where}: '{key}' must be a non-empty string")
    return value


def _price(value: Any, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise PriceBookError(f"{where} must be a number")
    try:
        price = Decimal(str(value))
    except InvalidOperation as exc:
        raise PriceBookError(f"{where} must be a number") from exc
    if not price.is_finite() or price < 0:
        raise PriceBookError(f"{where} must be a number of at least 0")
    return price


def _entry(node: Any, index: int) -> PriceEntry:
    where = f"models[{index}]"
    if not isinstance(node, dict):
        raise PriceBookError(f"{where} must be a mapping")
    unknown = set(node) - {"match", "provider", "effective_from", "per_mtok"}
    if unknown:
        raise PriceBookError(f"{where}: unknown keys {sorted(unknown)}")
    match = node.get("match")
    patterns = (match,) if isinstance(match, str) else match
    if (
        not isinstance(patterns, list | tuple)
        or not patterns
        or not all(isinstance(p, str) and p for p in patterns)
    ):
        raise PriceBookError(f"{where}: 'match' must be a pattern or a list of patterns")
    effective = node.get("effective_from")
    if not isinstance(effective, date) or isinstance(effective, datetime):
        raise PriceBookError(f"{where}: 'effective_from' must be a date (YYYY-MM-DD)")
    per_mtok = node.get("per_mtok")
    if not isinstance(per_mtok, dict) or set(per_mtok) != set(_PRICE_FIELDS):
        raise PriceBookError(f"{where}: 'per_mtok' must hold exactly {', '.join(_PRICE_FIELDS)}")
    prices = Prices(*(_price(per_mtok[name], f"{where}.per_mtok.{name}") for name in _PRICE_FIELDS))
    return PriceEntry(tuple(patterns), _text(node, "provider", where), effective, prices)


def parse_price_book(text: str) -> PriceBook:
    """Strict reading: every problem is a :class:`PriceBookError` naming it."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PriceBookError(f"not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PriceBookError("the price book must be a mapping")
    unknown = set(data) - {"version", "currency", "source_note", "models"}
    if unknown:
        raise PriceBookError(f"unknown keys {sorted(unknown)}")
    if data.get("currency") != CURRENCY:
        raise PriceBookError(f"'currency' must be {CURRENCY}")
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise PriceBookError("'models' must be a non-empty list")
    version = data.get("version")
    if not isinstance(version, str | int | float) or not str(version).strip():
        raise PriceBookError("'version' must be set")
    return PriceBook(
        version=str(version),
        currency=CURRENCY,
        source_note=_text(data, "source_note", "price book"),
        entries=tuple(_entry(node, i) for i, node in enumerate(models)),
    )


def load_shipped() -> PriceBook:
    """The book that ships with Tokli (package data; no CWD-relative read)."""
    text = resources.files("tokli.pricing").joinpath("price_book.yaml").read_text(encoding="utf-8")
    return parse_price_book(text)


def _specificity(pattern: str) -> tuple[int, int]:
    """Smaller sorts first: fewer wildcards, then more literal characters (TC-008)."""
    wildcards = pattern.count("*") + pattern.count("?")
    return wildcards, -(len(pattern) - wildcards)


def _best(book: PriceBook, model: str, day: date) -> PriceEntry | None:
    candidates: list[tuple[tuple[int, int], date, PriceEntry]] = []
    for entry in book.entries:
        if entry.effective_from > day:
            continue
        matching = [p for p in entry.match if fnmatch.fnmatchcase(model, p)]
        if matching:
            candidates.append((min(_specificity(p) for p in matching), entry.effective_from, entry))
    if not candidates:
        return None
    best = min(c[0] for c in candidates)
    return max((c for c in candidates if c[0] == best), key=lambda c: c[1])[2]


class PriceTable:
    """The effective prices: the user's book first, then the shipped one (TC-018)."""

    def __init__(self, shipped: PriceBook, user: PriceBook | None = None) -> None:
        self.shipped = shipped
        self.user = user

    def lookup(self, model: str | None, at: datetime) -> Match | None:
        if not model:
            return None
        day = at.astimezone(UTC).date()
        for book in (self.user, self.shipped):
            if book is None:
                continue
            entry = _best(book, model, day)
            if entry is not None:
                return Match(entry.prices, book.version)
        return None


def load_user(data_dir: Path) -> PriceBook | None:
    """The optional user book ``<data>/price-book.yaml`` (TC-018); a problem names the file."""
    path = data_dir / USER_FILE
    if not path.is_file():
        return None
    try:
        return parse_price_book(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise PriceBookError(f"{path}: cannot be read: {exc}") from exc
    except PriceBookError as exc:
        raise PriceBookError(f"{path}: {exc}") from exc
