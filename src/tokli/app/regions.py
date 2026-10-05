"""Where a request's saving sat among the provider's usage regions (TC-017, ADR 0014).

The provider reports, in order, how many tokens of the forwarded request were read from its
cache, written to it, and sent uncached. Tokli knows the forwarded position of every segment it
changed. Each saving is placed at its segment's forwarded span, the region sizes are converted to
estimate units with the request's ``k``, and the saving is split in proportion to the span's
overlap with each region. Integer parts use the largest remainder, so they sum exactly.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from tokli.compression.engine import Invocation
from tokli.domain.models import SegmentPlace
from tokli.domain.usage import Usage
from tokli.tokens.calibration import in_range

__all__ = ["RegionSplit", "SegmentPlace", "saving_regions", "split_for"]

Parts = tuple[int, int, int]  # cache read, cache write, uncached input


@dataclass(frozen=True)
class RegionSplit:
    request: Parts = (0, 0, 0)
    per_compressor: Mapping[str, Parts] = field(default_factory=dict)


def _fractions(start: float, length: float, read_end: float, write_end: float) -> list[float]:
    """The share of the span ``[start, start + length)`` in each region; an empty span is the
    point ``start``."""
    if length <= 0:
        if start < read_end:
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0] if start < write_end else [0.0, 0.0, 1.0]
    end = start + length
    read = max(0.0, min(end, read_end) - start)
    write = max(0.0, min(end, write_end) - max(start, read_end))
    return [read / length, write / length, max(0.0, length - read - write) / length]


def _integers(parts: list[float], total: int) -> Parts:
    """Largest remainder; ties go to the earlier region."""
    floors = [math.floor(p) for p in parts]
    missing = total - sum(floors)
    order = sorted(range(3), key=lambda i: (-(parts[i] - floors[i]), i))
    for i in order[: max(0, missing)]:
        floors[i] += 1
    return floors[0], floors[1], floors[2]


def saving_regions(
    places: Sequence[SegmentPlace],
    savings: Mapping[str, Mapping[str, int]],
    usage: tuple[int, int, int],
    k: float,
) -> RegionSplit:
    """``savings``: segment id → compressor id → tokens saved on it (estimate units).
    ``usage``: cache read, cache write and uncached input tokens (provider units)."""
    read_end = usage[0] / k
    write_end = read_end + usage[1] / k
    removed_before = 0
    shares: dict[str, list[float]] = {}
    totals: dict[str, int] = {}
    for place in sorted(places, key=lambda p: p.offset):
        by_compressor = savings.get(place.segment_id, {})
        saved = sum(by_compressor.values())
        forwarded_start = place.offset - removed_before
        fractions = _fractions(forwarded_start, place.length - saved, read_end, write_end)
        for cid, value in by_compressor.items():
            acc = shares.setdefault(cid, [0.0, 0.0, 0.0])
            for i in range(3):
                acc[i] += value * fractions[i]
            totals[cid] = totals.get(cid, 0) + value
        removed_before += saved
    per = {cid: _integers(shares[cid], totals[cid]) for cid in shares}
    request = (
        sum(p[0] for p in per.values()),
        sum(p[1] for p in per.values()),
        sum(p[2] for p in per.values()),
    )
    return RegionSplit(request, per)


def split_for(
    invocations: Sequence[Invocation],
    places: Sequence[SegmentPlace],
    usage: Usage,
    k: float | None,
) -> RegionSplit | None:
    """The split of a completed request, or ``None`` when TC-017 leaves it null: no complete
    provider usage, no in-range ``k``, or a changed segment without a place."""
    if usage.source != "provider" or not in_range(k) or not places:
        return None
    assert k is not None  # in_range(None) is false
    savings: dict[str, dict[str, int]] = {}
    for item in invocations:
        if item.decision == "accepted" and item.tokens_in > item.tokens_out:
            by = savings.setdefault(item.segment_id, {})
            by[item.compressor_id] = by.get(item.compressor_id, 0) + (
                item.tokens_in - item.tokens_out
            )
    if not savings:
        return None
    known = {place.segment_id for place in places}
    if not set(savings) <= known:
        return None
    regions = (
        usage.cache_read or 0,
        (usage.cache_write_5m or 0) + (usage.cache_write_1h or 0),
        usage.input or 0,
    )
    return saving_regions(places, savings, regions, k)
