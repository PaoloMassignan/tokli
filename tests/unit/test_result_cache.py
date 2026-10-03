"""CC-024 / AC-CC-13: the deterministic cache of compressor results."""

from __future__ import annotations

import dataclasses
import sys
import threading

from tests.helpers import make_request
from tests.unit.test_engine import Fake, run, settings_for, stats_of
from tokli.compression.contract import Applicability, SegmentView
from tokli.compression.engine import _ENTRY_OVERHEAD, Engine, ResultCache
from tokli.domain.models import SegmentKind, Span
from tokli.domain.stage import Features

TEXT = "a b c " * 40


def cached(*enabled: str, cache_bytes: int = 1_000_000):  # type: ignore[no-untyped-def]
    return settings_for(*enabled, result_cache_bytes=cache_bytes)


def comparable(stats):  # type: ignore[no-untyped-def]
    """Stats without wall time and cache counters, which legitimately differ between runs."""
    return [
        {
            k: v
            for k, v in dataclasses.asdict(s).items()
            if k not in {"ms_total", "cache_hits", "cache_misses"}
        }
        for s in stats
    ]


def test_result_cache_hit_gives_identical_output() -> None:
    fake = Fake()
    engine = Engine([fake], cached("fake"))
    request = make_request(("TOOL_RESULT", TEXT), ("USER_TEXT", TEXT + "x"))
    first = run(engine, request)
    calls = (fake.applicable_calls, fake.compress_calls)
    second = run(engine, request)
    assert (fake.applicable_calls, fake.compress_calls) == calls  # nothing recomputed
    assert second.patches == first.patches and second.patches
    assert comparable(second.stats) == comparable(first.stats)
    assert (stats_of(first, "fake").cache_hits, stats_of(first, "fake").cache_misses) == (0, 2)
    assert (stats_of(second, "fake").cache_hits, stats_of(second, "fake").cache_misses) == (2, 0)


def test_result_cache_also_caches_not_applicable_and_no_gain() -> None:
    not_applicable = Fake("na", applicable=False)
    no_gain = Fake("ng", transform=lambda t: t)
    engine = Engine([not_applicable, no_gain], cached("na", "ng"))
    request = make_request(("TOOL_RESULT", TEXT))
    first = run(engine, request)
    second = run(engine, request)
    assert not_applicable.applicable_calls == 1 and no_gain.compress_calls == 1
    assert comparable(second.stats) == comparable(first.stats)


def test_result_cache_key_includes_view_and_config() -> None:
    fake = Fake()
    engine = Engine([fake], cached("fake"))
    run(engine, make_request(("TOOL_RESULT", TEXT), tool_names=("ToolA",)))
    assert fake.compress_calls == 1
    run(engine, make_request(("TOOL_RESULT", TEXT), tool_names=("ToolB",)))
    assert fake.compress_calls == 2  # another tool name: another SegmentView
    request = make_request(("TOOL_RESULT", TEXT), tool_names=("ToolA",))
    run(engine, request, spans={"s0": [Span(0, 5, "reminder")]})
    assert fake.compress_calls == 3  # other protected spans
    verbatim = run(engine, make_request(("TOOL_RESULT", TEXT), tool_names=("Read",)))
    assert fake.compress_calls == 3 and verbatim.patches == ()  # verbatim tool: never served

    other_config = Engine([fake], cached("fake", cache_bytes=1_000_000))
    run(other_config, make_request(("TOOL_RESULT", TEXT), tool_names=("ToolA",)))
    assert fake.compress_calls == 4  # a cache belongs to one engine, i.e. one config


def test_result_cache_still_checks_invariants() -> None:
    """CC-005/CC-007 are applied to a cached result too."""
    fake = Fake(transform=lambda t: t.replace("a", ""))  # removes the protected "a b"
    engine = Engine([fake], cached("fake"))
    request = make_request(("TOOL_RESULT", TEXT))
    spans = {"s0": [Span(0, 3, "reminder")]}
    first = run(engine, request, spans=spans)
    second = run(engine, request, spans=spans)
    for result in (first, second):
        assert result.patches == ()
        assert stats_of(result, "fake").rejected_invariant == 1


def test_result_cache_bounded() -> None:
    fake = Fake()
    engine = Engine([fake], cached("fake", cache_bytes=20_000))
    for i in range(200):
        run(engine, make_request(("TOOL_RESULT", f"{i} " + TEXT)))
        assert engine.result_cache_bytes <= 20_000
    assert engine.result_cache_bytes > 0
    calls = fake.compress_calls
    run(engine, make_request(("TOOL_RESULT", "0 " + TEXT)))  # long evicted
    assert fake.compress_calls == calls + 1
    run(engine, make_request(("TOOL_RESULT", "199 " + TEXT)))  # most recent: still cached
    assert fake.compress_calls == calls + 1


def test_result_cache_off() -> None:
    fake = Fake()
    engine = Engine([fake], cached("fake", cache_bytes=0))
    request = make_request(("TOOL_RESULT", TEXT))
    run(engine, request)
    result = run(engine, request)
    assert fake.compress_calls == 2
    assert engine.result_cache_bytes == 0
    assert (stats_of(result, "fake").cache_hits, stats_of(result, "fake").cache_misses) == (0, 0)


def test_failed_result_is_not_cached() -> None:
    calls = {"n": 0}

    def flaky(text: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return text.replace(" ", "")

    fake = Fake(transform=flaky)
    engine = Engine([fake], cached("fake"))
    request = make_request(("TOOL_RESULT", TEXT))
    assert stats_of(run(engine, request), "fake").failed == 1
    assert stats_of(run(engine, request), "fake").accepted == 1


def test_result_cache_is_safe_under_concurrent_requests() -> None:
    """CC-024 with PX-015 (S4.5 D3, ADR 0011): transformations now run on worker threads and
    share the engine's cache. Concurrent lookups, insertions and evictions never raise, and the
    cache's size stays the sum of its entries.

    Root cause guarded against: ``get`` looked a key up and then moved it to the end; another
    thread could evict the key in between (``KeyError``), and two concurrent ``put`` calls
    could lose a size update."""
    cache = ResultCache(max_bytes=40 * (_ENTRY_OVERHEAD + 8))
    view = SegmentView(SegmentKind.TOOL_RESULT, "user", "Read", False, ())
    features = Features(tokens=8, json_candidate=False)
    keys = [cache.key("c", "1", view, features, f"text {i}") for i in range(200)]
    errors: list[BaseException] = []
    start = threading.Barrier(8)

    def worker(seed: int) -> None:
        start.wait()
        try:
            for n in range(20_000):
                key = keys[(seed * 7919 + n * 31) % len(keys)]
                if cache.get(key) is None:
                    cache.put(key, Applicability(True), "x" * 8)
        except BaseException as exc:
            errors.append(exc)

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=worker, args=(s,)) for s in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
    finally:
        sys.setswitchinterval(old)
    assert errors == []
    assert cache.size == sum(entry[2] for entry in cache._entries.values())
    assert cache.size <= 40 * (_ENTRY_OVERHEAD + 8)
