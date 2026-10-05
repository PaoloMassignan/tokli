"""SPEC 013 TC-017 (AC-TC-13): where each saving sits among the provider's usage regions."""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import FakeCounter
from tokli.app.regions import SegmentPlace, saving_regions
from tokli.domain.models import SegmentKind
from tokli.protocols.anthropic_messages import estimate_request_tokens, parse, segment_places


def test_saving_regions_hand_computed() -> None:
    """k = 1. Forwarded: A [0,100), B [100,300) (saved 100), C [300,350) (saved 150).
    Regions: cache read [0,250), cache write [250,330), uncached input after.
    B: 150/200 in read, 50/200 in write → 75 / 25 / 0. C: 30/50 in write, 20/50 uncached →
    0 / 90 / 60."""
    places = [SegmentPlace("A", 0, 100), SegmentPlace("B", 100, 300), SegmentPlace("C", 400, 200)]
    savings = {"B": {"json_minify": 100}, "C": {"reread_by_reference": 150}}
    split = saving_regions(places, savings, (250, 80, 1000), 1.0)
    assert split.per_compressor == {"json_minify": (75, 25, 0), "reread_by_reference": (0, 90, 60)}
    assert split.request == (75, 115, 60)


def test_saving_regions_scale_by_k() -> None:
    """k = 2 halves the region sizes in estimate units: read [0,125), write [125,165).
    B [100,300): 25 / 40 / 135 of 200 → 12.5 / 20 / 67.5 → 13 / 20 / 67 (largest remainder,
    ties to the earlier region)."""
    places = [SegmentPlace("A", 0, 100), SegmentPlace("B", 100, 300)]
    split = saving_regions(places, {"B": {"json_minify": 100}}, (250, 80, 1000), 2.0)
    assert split.request == (13, 20, 67)


def test_saving_in_an_emptied_segment_sits_at_its_offset() -> None:
    """A segment reduced to nothing is placed at its forwarded offset."""
    places = [SegmentPlace("A", 0, 100), SegmentPlace("B", 100, 50)]
    split = saving_regions(places, {"B": {"x": 50}}, (90, 20, 0), 1.0)
    assert split.request == (0, 50, 0)  # forwarded B is the point 100, inside [90, 110)


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.tuples(st.integers(1, 500), st.integers(0, 500), st.integers(0, 3)),
        min_size=1,
        max_size=12,
    ),
    st.tuples(st.integers(0, 3000), st.integers(0, 3000), st.integers(0, 3000)),
    st.sampled_from([0.5, 0.8, 1.0, 1.3, 2.0]),
)
def prop_saving_regions_sum_to_saving(
    segments: list[tuple[int, int, int]], usage: tuple[int, int, int], k: float
) -> None:
    """AC-TC-13: the parts sum to the saving, per compressor and per request."""
    places, savings, offset = [], {}, 0
    for i, (length, saved, compressor) in enumerate(segments):
        places.append(SegmentPlace(f"s{i}", offset, length))
        offset += length
        saved = min(saved, length)
        if saved:
            savings[f"s{i}"] = {f"c{compressor}": saved}
    split = saving_regions(places, savings, usage, k)
    per: dict[str, int] = {}
    for by in savings.values():
        for cid, value in by.items():
            per[cid] = per.get(cid, 0) + value
    assert {cid: sum(parts) for cid, parts in split.per_compressor.items()} == per
    assert sum(split.request) == sum(per.values())
    assert all(part >= 0 for parts in split.per_compressor.values() for part in parts)


def test_segment_places_follow_provider_order() -> None:
    """TC-017: tool definitions, then system, then messages, whatever the JSON key order; the
    places cover the whole-request estimate."""
    body = {
        "messages": [
            {"role": "user", "content": "first question"},
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x" * 300}],
            },
        ],
        "model": "claude-test",
        "system": "a synthetic system prompt",
        "tools": [{"name": "Read", "description": "reads a file", "input_schema": {}}],
        "max_tokens": 10,
    }
    request = parse(json.dumps(body).encode(), mutable_kinds=frozenset({SegmentKind.TOOL_RESULT}))
    counter = FakeCounter()
    places = {p.segment_id: p for p in segment_places(request, counter.count)}
    by_kind = {s.kind: s.id for s in request.segments}
    system = places[by_kind[SegmentKind.SYSTEM]]
    result = places[by_kind[SegmentKind.TOOL_RESULT]]
    tool = places[by_kind[SegmentKind.TOOL_DESCRIPTION]]
    assert tool.offset < system.offset < result.offset
    assert result.length == 300
    total = estimate_request_tokens(request, counter.count)
    assert max(p.offset + p.length for p in places.values()) <= total
