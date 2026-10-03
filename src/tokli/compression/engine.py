"""Compression engine (SPEC 009): filters, acceptance gate, invariants, timing and statistics.

S1 policy is fixed to LOSSLESS_ONLY (A7). Chains of several compressors are exercised from S4
(decision C3), but the loop already applies compressors in ``(stage, id)`` order.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from tokli.compression.contract import Applicability, Compressor, SegmentView
from tokli.domain.models import CanonicalRequest, Patch, Segment, SegmentKind
from tokli.domain.spans import spans_preserved
from tokli.domain.stage import Features, StageView

POLICY = "LOSSLESS_ONLY"
_PERMITTED_KINDS = frozenset({"LOSSLESS"})
_STAGE_ORDER = {"normalize": 0, "structural": 1, "domain": 2, "semantic": 3}


class Counter(Protocol):
    def count(self, text: str) -> int: ...


@dataclass(frozen=True)
class EngineSettings:
    enabled: Mapping[str, bool]
    verbatim_tools: frozenset[str]
    min_segment_tokens: int = 64
    min_gain_tokens: int = 4
    min_gain_ratio: float = 0.01
    request_budget_ms: float = 50.0
    per_call_timeout_ms: float = 200.0
    verify_lossless: bool = False
    result_cache_bytes: int = 0


@dataclass
class CompressorStats:
    """Per request and compressor (TOKLI_TELEMETRY_AND_COST §2)."""

    compressor_id: str
    compressor_version: str
    kind: str
    considered: int = 0
    applicable: int = 0
    accepted: int = 0
    rejected_no_gain: int = 0
    rejected_invariant: int = 0
    failed: int = 0
    skipped_budget: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    ms_total: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def marginal_saved(self) -> int:
        return self.tokens_in - self.tokens_out


@dataclass(frozen=True)
class Invocation:
    segment_id: str
    compressor_id: str
    decision: str  # skipped | not_applicable | accepted | rejected | failed
    reason: str
    tokens_in: int
    tokens_out: int
    ms: float


@dataclass(frozen=True)
class EngineResult:
    patches: tuple[Patch, ...]
    stats: tuple[CompressorStats, ...]
    invocations: tuple[Invocation, ...]
    est_original_tokens: int
    est_forwarded_tokens: int
    segments_mutable: int
    segments_changed: int

    @property
    def any_applicable(self) -> bool:
        return any(s.applicable for s in self.stats)


Clock = Callable[[], float]

# Fixed per-entry bookkeeping counted against the cache bound (key, tuples, dict slot).
_ENTRY_OVERHEAD = 256


class ResultCache:
    """Results of ``applicable()`` + ``compress()`` per compressor input (CC-024).

    The key holds everything CC-006 lets a segment-scope result depend on: compressor id and
    version, the ``SegmentView``, the routing features and the text (SHA-256 and length). The
    effective config is fixed per engine, and each engine owns its cache. Least recently used
    entries are evicted past ``max_bytes``, an approximate measure (text characters plus a fixed
    overhead per entry).
    """

    def __init__(self, max_bytes: int) -> None:
        self._max = max_bytes
        self._entries: OrderedDict[Any, tuple[Applicability, str | None, int]] = OrderedDict()
        self.size = 0

    @staticmethod
    def key(spec_id: str, version: str, view: SegmentView, features: Features, text: str) -> Any:
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()
        return (spec_id, version, view, features, len(text), digest)

    def get(self, key: Any) -> tuple[Applicability, str | None] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry[0], entry[1]

    def put(self, key: Any, applicability: Applicability, output: str | None) -> None:
        size = _ENTRY_OVERHEAD + len(output or "")
        if size > self._max:
            return
        old = self._entries.pop(key, None)
        if old is not None:
            self.size -= old[2]
        self._entries[key] = (applicability, output, size)
        self.size += size
        while self.size > self._max:
            _, (_, _, evicted) = self._entries.popitem(last=False)
            self.size -= evicted


def availability_of(requires: Sequence[str]) -> str:
    """``available`` or ``unavailable(<first missing module>)`` (CC-010)."""
    for module in requires:
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            return f"unavailable({module})"
    return "available"


def _features(text: str, counter: Counter) -> Features:
    stripped = text.strip()
    return Features(
        tokens=counter.count(text),
        json_candidate=bool(stripped) and stripped[0] in "{[" and stripped[-1] in "}]",
    )


class Engine:
    def __init__(
        self,
        registry: Sequence[Compressor],
        settings: EngineSettings,
        clock: Clock = time.perf_counter,
    ) -> None:
        self._compressors = tuple(
            sorted(registry, key=lambda c: (_STAGE_ORDER[c.spec.stage], c.spec.id))
        )
        self._settings = settings
        self._clock = clock
        self._availability = {
            c.spec.id: availability_of(c.spec.requires) for c in self._compressors
        }
        self._cache = (
            ResultCache(settings.result_cache_bytes) if settings.result_cache_bytes else None
        )

    @property
    def result_cache_bytes(self) -> int:
        """Current size of the result cache (CC-024), 0 when it is off."""
        return self._cache.size if self._cache is not None else 0

    def availability(self) -> dict[str, str]:
        """``available`` or ``unavailable(<module>)`` per compressor (CC-010)."""
        return dict(self._availability)

    def _pre_filter(self, compressor: Compressor) -> str:
        spec = compressor.spec
        if not self._settings.enabled.get(spec.id, False):
            return "disabled"
        if spec.kind not in _PERMITTED_KINDS:
            return f"policy_forbids({spec.kind})"
        availability = self._availability[spec.id]
        return "" if availability == "available" else availability

    def run(self, request: CanonicalRequest, view: StageView, counter: Counter) -> EngineResult:
        start = self._clock()
        stats = {
            c.spec.id: CompressorStats(c.spec.id, c.spec.version, c.spec.kind)
            for c in self._compressors
        }
        invocations: list[Invocation] = []
        patches: list[Patch] = []
        est_original = est_forwarded = mutable = changed = 0

        for segment in request.segments:
            if not segment.mutable:
                continue
            mutable += 1
            original = view.texts.get(segment.id, segment.text)
            text, accepted_by = self._run_segment(
                segment, original, view, counter, start, stats, invocations
            )
            est_original += counter.count(original)
            est_forwarded += counter.count(text)
            if text != original:
                changed += 1
                patches.append(Patch(segment.id, text, tuple(accepted_by)))

        return EngineResult(
            patches=tuple(patches),
            stats=tuple(stats.values()),
            invocations=tuple(invocations),
            est_original_tokens=est_original,
            est_forwarded_tokens=est_forwarded,
            segments_mutable=mutable,
            segments_changed=changed,
        )

    def _run_segment(
        self,
        segment: Segment,
        original: str,
        view: StageView,
        counter: Counter,
        start: float,
        stats: dict[str, CompressorStats],
        invocations: list[Invocation],
    ) -> tuple[str, list[str]]:
        settings = self._settings
        spans = tuple(view.spans.get(segment.id, ()))
        features = view.features.get(segment.id) or _features(original, counter)
        segment_view = SegmentView(
            kind=segment.kind,
            role=segment.role,
            tool_name=segment.tool_name,
            is_error=segment.is_error,
            protected=spans,
        )
        text = original
        accepted_by: list[str] = []
        terminal_reached = False

        for compressor in self._compressors:
            spec = compressor.spec
            stat = stats[spec.id]

            def record(
                decision: str, reason: str, t_in: int = 0, t_out: int = 0, ms: float = 0.0
            ) -> None:
                invocations.append(
                    Invocation(segment.id, spec.id, decision, reason, t_in, t_out, ms)  # noqa: B023
                )

            def skip(reason: str, detail: str = "") -> None:
                stat.skip_reasons[reason] = stat.skip_reasons.get(reason, 0) + 1  # noqa: B023
                record("skipped", detail or reason)

            reason = self._pre_filter(compressor)
            if reason:
                skip(reason)
                continue
            stat.considered += 1
            if segment.kind not in spec.segment_kinds:
                skip("kind_not_supported")
                continue
            t_in = counter.count(text)
            if t_in < max(spec.min_tokens, settings.min_segment_tokens):
                skip("too_small")
                continue
            if segment.kind is SegmentKind.TOOL_RESULT and spec.equivalence != "reference":
                if segment.tool_name is None:
                    skip("verbatim_tool", "verbatim_tool(unresolved)")
                    continue
                if segment.tool_name in settings.verbatim_tools:
                    skip("verbatim_tool")
                    continue
            if terminal_reached:
                skip("after_terminal")
                continue
            if (self._clock() - start) * 1000 >= settings.request_budget_ms:
                stat.skipped_budget += 1
                skip("budget_exhausted")
                continue

            call_start = self._clock()
            cache, key, hit = self._cache, None, None
            if cache is not None:
                key = cache.key(spec.id, spec.version, segment_view, features, text)
                hit = cache.get(key)
            if hit is not None:
                stat.cache_hits += 1
                applicability, output = hit
            else:
                if cache is not None:
                    stat.cache_misses += 1
                try:
                    applicability = compressor.applicable(text, segment_view, features)
                    output = compressor.compress(text, segment_view) if applicability.ok else None
                except Exception:  # isolation (CC-008): a compressor never fails the request
                    ms = (self._clock() - call_start) * 1000
                    stat.ms_total += ms
                    stat.failed += 1
                    record("failed", "exception", ms=ms)
                    continue
            ms = (self._clock() - call_start) * 1000
            stat.ms_total += ms
            if cache is not None and hit is None and ms <= settings.per_call_timeout_ms:
                cache.put(key, applicability, output)  # failures and timeouts are not cached

            if not applicability.ok:
                code = f"not_applicable({applicability.reason})"
                stat.skip_reasons[code] = stat.skip_reasons.get(code, 0) + 1
                record("not_applicable", code, ms=ms)
                continue
            stat.applicable += 1
            stat.tokens_in += t_in

            if ms > settings.per_call_timeout_ms:
                stat.failed += 1
                stat.tokens_out += t_in
                record("failed", "timeout", t_in, t_in, ms)
                continue
            if output is None or output == text:
                stat.rejected_no_gain += 1
                stat.tokens_out += t_in
                record("rejected", "no_gain", t_in, t_in, ms)
                continue
            if not spans_preserved(original, spans, output):
                stat.rejected_invariant += 1
                stat.tokens_out += t_in
                record("rejected", "protected_span_changed", t_in, t_in, ms)
                continue
            t_out = counter.count(output)
            required = max(settings.min_gain_tokens, math.ceil(t_in * settings.min_gain_ratio))
            if t_out > t_in - required:
                stat.rejected_no_gain += 1
                stat.tokens_out += t_in
                record("rejected", "no_gain" if t_out >= t_in else "below_min_gain", t_in, t_in, ms)
                continue
            if settings.verify_lossless and spec.kind == "LOSSLESS":
                decode = getattr(compressor, "decode", None)
                equivalent = getattr(compressor, "equivalent", None)
                if decode is None or equivalent is None or not equivalent(text, decode(output)):
                    stat.rejected_invariant += 1
                    stat.tokens_out += t_in
                    record("rejected", "decode_mismatch", t_in, t_in, ms)
                    continue

            stat.accepted += 1
            stat.tokens_out += t_out
            record("accepted", "", t_in, t_out, ms)
            text = output
            accepted_by.append(spec.id)
            terminal_reached = terminal_reached or spec.terminal

        return text, accepted_by
