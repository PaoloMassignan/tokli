"""AN-005…AN-007, AN-009, AN-010, TM-003: provider usage from Anthropic responses and streams."""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from tokli.protocols.anthropic_usage import BodyUsageParser, StreamUsageParser, unavailable

RESPONSES = Path(__file__).resolve().parents[1] / "compat" / "fixtures" / "anthropic_responses"
LIMIT = 1024 * 1024


def fixture(name: str) -> bytes:
    return (RESPONSES / name).read_bytes()


def categories(usage):  # type: ignore[no-untyped-def]
    return (
        usage.input,
        usage.cache_read,
        usage.cache_write_5m,
        usage.cache_write_1h,
        usage.output,
    )


def stream(data: bytes, pieces: list[bytes] | None = None):  # type: ignore[no-untyped-def]
    parser = StreamUsageParser(LIMIT)
    for piece in pieces if pieces is not None else [data]:
        parser.feed(piece)
    return parser.result()


def body(data: bytes, limit: int = LIMIT):  # type: ignore[no-untyped-def]
    parser = BodyUsageParser(limit)
    parser.feed(data)
    return parser.result()


def test_anthropic_usage_non_stream() -> None:
    usage = body(fixture("non_stream.json"))
    assert usage.source == "provider" and usage.reason is None
    assert categories(usage) == (12, 4000, 0, 500, 7)
    assert usage.input_total == 12 + 4000 + 0 + 500


def test_anthropic_usage_non_stream_without_cache_split() -> None:
    """TELEMETRY_AND_COST §4: without `cache_creation`, `cache_creation_input_tokens` is 5m."""
    usage = body(fixture("non_stream_without_cache_split.json"))
    assert categories(usage) == (12, 0, 300, 0, 7)


def test_anthropic_usage_stream() -> None:
    usage = stream(fixture("stream_basic.sse"))
    assert usage.source == "provider" and usage.reason is None
    assert categories(usage) == (25, 30000, 1000, 200, 15)
    assert usage.input_total == 31225
    assert usage.events == {
        "message_start": 1,
        "content_block_start": 1,
        "ping": 1,
        "content_block_delta": 1,
        "content_block_stop": 1,
        "message_delta": 1,
        "message_stop": 1,
    }


def test_anthropic_usage_stream_last_value_per_field_wins() -> None:
    usage = stream(fixture("stream_cumulative_delta.sse"))
    assert categories(usage) == (40, 30000, 0, 0, 22)


def test_anthropic_usage_stream_with_error_event() -> None:
    """AC-AN-3 / AN-010: input from `message_start` only, flagged partial."""
    usage = stream(fixture("stream_error_event.sse"))
    assert usage.source == "provider_partial"
    assert categories(usage) == (25, 30000, 1000, 200, 1)
    assert usage.input_total == 31225
    assert usage.events["error"] == 1


def test_stream_cut_after_message_start_is_partial() -> None:
    data = fixture("stream_basic.sse")
    cut = data[: data.index(b"event: message_delta")]
    parser = StreamUsageParser(LIMIT)
    parser.feed(cut)
    usage = parser.result(disconnected=True)
    assert usage.source == "provider_partial"
    assert categories(usage) == (25, 30000, 1000, 200, 1)


def test_usage_parser_failure_is_unavailable() -> None:
    """AN-007 / AC-AN-6: every way of not getting usage gives `unavailable` and a reason."""
    assert body(b'{"type":"message"').reason == "usage_unavailable(parse_error)"
    assert body(b'{"type":"message","content":[]}').reason == "usage_unavailable(no_usage)"
    assert stream(b"event: ping\ndata: {}\n\n").reason == "usage_unavailable(no_usage)"
    assert (
        stream(b"event: message_start\ndata: {not json\n\n").reason
        == "usage_unavailable(parse_error)"
    )
    parser = StreamUsageParser(LIMIT)
    parser.feed(b"event: ping\ndata: {}\n\n")
    assert parser.result(disconnected=True).reason == "usage_unavailable(client_disconnected)"
    for why in ("upstream_status", "content_encoding"):
        usage = unavailable(why)
        assert usage.source == "unavailable" and usage.reason == f"usage_unavailable({why})"
        assert categories(usage) == (None, None, None, None, None)
        assert usage.input_total is None
    for usage in (body(b"{"), stream(b"")):
        assert usage.source == "unavailable"
        assert categories(usage) == (None, None, None, None, None)


def test_usage_parser_memory_bounded() -> None:
    """AN-009: past the bound the parser stops parsing and holds no more data."""
    big_event = b"event: content_block_delta\ndata: " + b"x" * 5000  # no end of line yet
    parser = StreamUsageParser(4096)
    parser.feed(big_event)
    parser.feed(b"y" * 100_000)
    assert parser.buffered_bytes == 0
    assert parser.result().reason == "usage_unavailable(buffer_limit)"

    padded = json.dumps({"content": [{"type": "text", "text": "z" * 10_000}], "usage": {}})
    collector = BodyUsageParser(4096)
    collector.feed(padded.encode())
    collector.feed(b" " * 100_000)
    assert collector.buffered_bytes == 0
    assert collector.result().reason == "usage_unavailable(buffer_limit)"


def test_usage_parser_ignores_large_uninteresting_events_within_bound() -> None:
    """Many content events in a row stay within the bound: only the current event is held."""
    delta = json.dumps(
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "q"}}
    )
    data = fixture("stream_basic.sse").replace(
        b"event: message_delta",
        f"event: content_block_delta\ndata: {delta}\n\n".encode() * 2000 + b"event: message_delta",
    )
    usage = stream(data)
    assert usage.source == "provider" and usage.events["content_block_delta"] == 2001


def _with_line_endings(data: bytes, ending: bytes) -> bytes:
    return data.replace(b"\n", ending)


@settings(max_examples=150, deadline=None)
@given(
    ending=st.sampled_from([b"\n", b"\r\n", b"\r"]),
    cuts=st.lists(st.integers(min_value=0, max_value=4000), max_size=40),
)
def prop_usage_stream_any_chunk_split(ending: bytes, cuts: list[int]) -> None:
    """Events may be split anywhere across chunks (inside a CR LF pair or a UTF-8 character)."""
    data = _with_line_endings(fixture("stream_basic.sse"), ending)
    points = sorted({c % (len(data) + 1) for c in cuts})
    pieces = [data[a:b] for a, b in zip([0, *points], [*points, len(data)], strict=True)]
    usage = stream(data, pieces)
    assert usage.source == "provider"
    assert categories(usage) == (25, 30000, 1000, 200, 15)
    assert usage.events["message_stop"] == 1


def test_stream_records_usage_field_names_of_message_delta() -> None:
    """E4 / Q3: which usage fields `message_delta` carries (names only) is recorded."""
    assert stream(fixture("stream_basic.sse")).delta_fields == ("output_tokens",)
    assert stream(fixture("stream_cumulative_delta.sse")).delta_fields == (
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "input_tokens",
        "output_tokens",
    )


def test_message_delta_without_split_keeps_cache_split_from_message_start() -> None:
    """Regression (found in live test E4, 2026-10-03): the real `message_delta` repeats
    `cache_creation_input_tokens` cumulatively but without the `cache_creation` 5m/1h object.
    Root cause: the parser applied the "no split → all 5m" fallback to the delta and overwrote
    the split read from `message_start`, so 1h cache writes were reported as 5m."""
    usage = stream(fixture("stream_cumulative_delta_without_split.sse"))
    assert categories(usage) == (3, 30000, 1000, 200, 42)
    assert usage.source == "provider"
    assert "iterations" in usage.delta_fields  # unknown fields are named, never parsed
