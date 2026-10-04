"""Compression engine (SPEC 009): filters, acceptance gate, invariants, timing and statistics.

Request-scope compressors (pruners) run first, then segment-scope compressors, each ordered by
``(stage, id)`` (PR-010, CC-009). Enabling a compressor is the only gate (CC-002 after S4
SCR-001); the request's policy is derived from the enabled kinds. Reference stubs are protected by
the reference-integrity check (CC-019, ADR 0010).
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from tokli.compression import text_shapes
from tokli.compression.contract import (
    AnyCompressor,
    Applicability,
    LosslessCompressor,
    RequestCompressor,
    SegmentRef,
    SegmentView,
    ToolRecordView,
)
from tokli.domain.models import CanonicalRequest, Patch, Segment, SegmentKind, Span
from tokli.domain.spans import spans_preserved
from tokli.domain.stage import Features, StageView

LOSSLESS_ONLY = "LOSSLESS_ONLY"
LOSSY_ALLOWED = "LOSSY_ALLOWED"
_TARGET_SAFE = frozenset({"byte", "structural"})  # may change a reference target (CC-019)
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
    verbatim_opt_in: frozenset[str] = frozenset()  # CC-021 (b), S8a SCR-001


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
    tokens_in_accepted: int = 0
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
    reference_stubs: int = 0

    @property
    def any_applicable(self) -> bool:
        return any(s.applicable for s in self.stats)


Clock = Callable[[], float]


@dataclass
class _RequestState:
    """What the request-scope phase leaves for the segment phase."""

    texts: dict[str, str]
    chains: dict[str, list[str]]
    terminal: set[str] = field(default_factory=set)
    targets: dict[str, list[str]] = field(default_factory=dict)  # target id -> stub ids


CacheKey = tuple[str, str, SegmentView, Features, int, bytes]
# Fixed per-entry bookkeeping counted against the cache bound (key, tuples, dict slot).
_ENTRY_OVERHEAD = 256


class ResultCache:
    """Results of ``applicable()`` + ``compress()`` per compressor input (CC-024).

    The key holds everything CC-006 lets a segment-scope result depend on: compressor id and
    version, the ``SegmentView``, the routing features and the text (SHA-256 and length). The
    effective config is fixed per engine, and each engine owns its cache. Least recently used
    entries are evicted past ``max_bytes``, an approximate measure (text characters plus a fixed
    overhead per entry). Requests are transformed on worker threads (PX-015, ADR 0011), so
    lookups and insertions hold a lock; compressors run outside it.
    """

    def __init__(self, max_bytes: int) -> None:
        self._max = max_bytes
        self._entries: OrderedDict[CacheKey, tuple[Applicability, str | None, int]] = OrderedDict()
        self.size = 0
        self._lock = threading.Lock()

    @staticmethod
    def key(
        spec_id: str, version: str, view: SegmentView, features: Features, text: str
    ) -> CacheKey:
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()
        return (spec_id, version, view, features, len(text), digest)

    def get(self, key: CacheKey) -> tuple[Applicability, str | None] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return entry[0], entry[1]

    def put(self, key: CacheKey, applicability: Applicability, output: str | None) -> None:
        size = _ENTRY_OVERHEAD + len(output or "")
        if size > self._max:
            return
        with self._lock:
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
    grep_lines, leveled, lines, crlf = text_shapes.shape_counts(text)
    return Features(
        tokens=counter.count(text),
        json_candidate=bool(stripped) and stripped[0] in "{[" and stripped[-1] in "}]",
        grep_lines=grep_lines,
        leveled_ratio=leveled / lines if lines else 0.0,
        line_count=lines,
        crlf=crlf,
    )


class Engine:
    def __init__(
        self,
        registry: Sequence[AnyCompressor],
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
        # Split by scope once: a runtime protocol check costs microseconds, too much to repeat
        # for every segment of a large request.
        self._request_scope = tuple(
            c
            for c in self._compressors
            if c.spec.scope == "request" and isinstance(c, RequestCompressor)
        )
        self._segment_scope = tuple(
            c
            for c in self._compressors
            if c.spec.scope != "request" and not isinstance(c, RequestCompressor)
        )
        self._decoders = {
            c.spec.id: c for c in self._segment_scope if isinstance(c, LosslessCompressor)
        }

    @property
    def compressors(self) -> tuple[AnyCompressor, ...]:
        return self._compressors

    @property
    def policy(self) -> str:
        """``LOSSLESS_ONLY`` when every enabled compressor is LOSSLESS (CC-002, S4 SCR-001)."""
        enabled = [c for c in self._compressors if self._settings.enabled.get(c.spec.id, False)]
        return LOSSLESS_ONLY if all(c.spec.kind == "LOSSLESS" for c in enabled) else LOSSY_ALLOWED

    @property
    def result_cache_bytes(self) -> int:
        """Current size of the result cache (CC-024), 0 when it is off."""
        return self._cache.size if self._cache is not None else 0

    def availability(self) -> dict[str, str]:
        """``available`` or ``unavailable(<module>)`` per compressor (CC-010)."""
        return dict(self._availability)

    def _pre_filter(self, compressor: AnyCompressor) -> str:
        spec = compressor.spec
        if not self._settings.enabled.get(spec.id, False):
            return "disabled"
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
        est_original = est_forwarded = changed = 0
        segments = [s for s in request.segments if s.mutable]
        originals = {s.id: view.texts.get(s.id, s.text) for s in segments}
        state = _RequestState(texts=dict(originals), chains={s.id: [] for s in segments})
        self._run_request_scope(
            request, segments, originals, view, counter, start, stats, invocations, state
        )

        for segment in segments:
            original = originals[segment.id]
            text, accepted_by = self._run_segment(
                segment,
                original,
                state.texts[segment.id],
                state.chains[segment.id],
                segment.id in state.terminal,
                segment.id in state.targets,
                view,
                counter,
                start,
                stats,
                invocations,
            )
            est_original += counter.count(original)
            est_forwarded += counter.count(text)
            if text != original:
                changed += 1
                patches.append(Patch(segment.id, text, tuple(accepted_by)))
        mutable = len(segments)

        return EngineResult(
            patches=tuple(patches),
            stats=tuple(stats.values()),
            invocations=tuple(invocations),
            est_original_tokens=est_original,
            est_forwarded_tokens=est_forwarded,
            segments_mutable=mutable,
            segments_changed=changed,
            reference_stubs=sum(len(stubs) for stubs in state.targets.values()),
        )

    def _gate(
        self,
        original: str,
        spans: Sequence[Span],
        text: str,
        output: str | None,
        t_in: int,
        counter: Counter,
    ) -> tuple[str, int]:
        """The acceptance gate shared by both scopes: ``("", t_out)`` to accept, else the
        rejection reason and the tokens kept."""
        settings = self._settings
        if output is None or output == text:
            return "no_gain", t_in
        if not spans_preserved(original, spans, output):
            return "protected_span_changed", t_in
        t_out = counter.count(output)
        required = max(settings.min_gain_tokens, math.ceil(t_in * settings.min_gain_ratio))
        if t_out > t_in - required:
            return ("no_gain" if t_out >= t_in else "below_min_gain"), t_in
        return "", t_out

    def _run_request_scope(
        self,
        request: CanonicalRequest,
        segments: Sequence[Segment],
        originals: Mapping[str, str],
        view: StageView,
        counter: Counter,
        start: float,
        stats: dict[str, CompressorStats],
        invocations: list[Invocation],
        state: _RequestState,
    ) -> None:
        """Pruners (PR-001, PR-010): each proposal passes the same gate as a segment result, plus
        reference integrity (CC-019), and is attributed to its compressor."""
        settings = self._settings
        tools = tuple(ToolRecordView(t.call_id, t.name, t.arguments) for t in request.tools)
        position = {s.id: i for i, s in enumerate(segments)}
        for compressor in self._request_scope:
            spec = compressor.spec
            stat = stats[spec.id]
            candidates = [s for s in segments if s.kind in spec.segment_kinds]

            def skip_all(reason: str) -> None:
                stat.skip_reasons[reason] = stat.skip_reasons.get(reason, 0) + len(candidates)  # noqa: B023
                for s in candidates:  # noqa: B023
                    invocations.append(Invocation(s.id, spec.id, "skipped", reason, 0, 0, 0.0))  # noqa: B023

            reason = self._pre_filter(compressor)
            if reason:
                skip_all(reason)
                continue
            stat.considered += len(candidates)
            if (self._clock() - start) * 1000 >= settings.request_budget_ms:
                stat.skipped_budget += len(candidates)
                skip_all("budget_exhausted")
                continue
            refs = [
                SegmentRef(
                    s.id,
                    SegmentView(
                        s.kind, s.role, s.tool_name, s.is_error, tuple(view.spans.get(s.id, ()))
                    ),
                    s.tool_call_id,
                    s.whole_result,
                )
                for s in candidates
                if s.id not in state.terminal
            ]
            call_start = self._clock()
            try:
                proposals = compressor.plan(
                    refs,
                    {r.segment_id: state.texts[r.segment_id] for r in refs},
                    tools,
                    counter.count,
                )
            except Exception:  # isolation (CC-008)
                ms = (self._clock() - call_start) * 1000
                stat.ms_total += ms
                stat.failed += 1
                invocations.append(Invocation("*", spec.id, "failed", "exception", 0, 0, ms))
                continue
            ms = (self._clock() - call_start) * 1000
            stat.ms_total += ms
            proposed = {p.segment_id for p in proposals}
            quiet = sum(1 for r in refs if r.segment_id not in proposed)
            if quiet:
                stat.skip_reasons["not_applicable(no_proposal)"] = (
                    stat.skip_reasons.get("not_applicable(no_proposal)", 0) + quiet
                )
            for declined in (p for p in proposals if p.new_text is None):
                code = f"not_applicable({declined.reason or 'no_proposal'})"
                stat.skip_reasons[code] = stat.skip_reasons.get(code, 0) + 1
                invocations.append(
                    Invocation(declined.segment_id, spec.id, "not_applicable", code, 0, 0, 0.0)
                )
            by_ref = {r.segment_id: r for r in refs}
            for proposal in proposals:
                new_text = proposal.new_text
                if new_text is None:
                    continue  # declined, recorded above
                sid = proposal.segment_id
                ref = by_ref.get(sid)
                if ref is None:
                    continue  # a proposal for a segment the compressor was not given
                text = state.texts[sid]
                t_in = counter.count(text)

                def record(decision: str, why: str, t_out: int = t_in) -> None:
                    invocations.append(Invocation(sid, spec.id, decision, why, t_in, t_out, 0.0))  # noqa: B023

                if t_in < max(spec.min_tokens, settings.min_segment_tokens):
                    stat.skip_reasons["too_small"] = stat.skip_reasons.get("too_small", 0) + 1
                    record("skipped", "too_small")
                    continue
                stat.applicable += 1
                stat.tokens_in += t_in
                target = proposal.target_id
                broken = sid in state.targets or (
                    target is not None
                    and (
                        target not in position
                        or position[target] >= position[sid]
                        or target in state.terminal
                        or state.texts[target] != originals[target]
                    )
                )
                if broken:
                    stat.rejected_invariant += 1
                    stat.tokens_out += t_in
                    record("rejected", "reference_target_modified")
                    continue
                why, t_out = self._gate(
                    originals[sid], ref.view.protected, text, new_text, t_in, counter
                )
                if why:
                    stat.rejected_no_gain += why != "protected_span_changed"
                    stat.rejected_invariant += why == "protected_span_changed"
                    stat.tokens_out += t_in
                    record("rejected", why)
                    continue
                if (
                    settings.verify_lossless
                    and spec.equivalence == "reference"
                    and target is not None
                ):
                    decoded = compressor.decode_request(
                        {sid: new_text, target: state.texts[target]}, refs
                    )
                    if decoded.get(sid) != originals[sid]:
                        stat.rejected_invariant += 1
                        stat.tokens_out += t_in
                        record("rejected", "decode_mismatch")
                        continue
                stat.accepted += 1
                stat.tokens_in_accepted += t_in
                stat.tokens_out += t_out
                record("accepted", "", t_out)
                state.texts[sid] = new_text
                state.chains[sid].append(spec.id)
                if spec.terminal:
                    state.terminal.add(sid)
                if target is not None:
                    state.targets.setdefault(target, []).append(sid)

    def _run_segment(
        self,
        segment: Segment,
        original: str,
        text: str,
        accepted_by: list[str],
        terminal_reached: bool,
        is_target: bool,
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
        for compressor in self._segment_scope:
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
                opted_in = spec.id in settings.verbatim_opt_in  # CC-021 (b), S8a SCR-001
                if segment.tool_name in settings.verbatim_tools and not opted_in:
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
            fresh = hit is None and ms <= settings.per_call_timeout_ms
            if cache is not None and key is not None and fresh:
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
            why, t_out = self._gate(original, spans, text, output, t_in, counter)
            if why:
                stat.rejected_no_gain += why != "protected_span_changed"
                stat.rejected_invariant += why == "protected_span_changed"
                stat.tokens_out += t_in
                record("rejected", why, t_in, t_in, ms)
                continue
            assert output is not None  # the gate accepts only a real output
            if is_target and spec.equivalence not in _TARGET_SAFE:  # CC-019
                stat.rejected_invariant += 1
                stat.tokens_out += t_in
                record("rejected", "reference_target_modified", t_in, t_in, ms)
                continue
            decoder = self._decoders.get(spec.id)
            if (
                settings.verify_lossless
                and spec.kind == "LOSSLESS"
                and not (decoder is not None and decoder.equivalent(text, decoder.decode(output)))
            ):
                stat.rejected_invariant += 1
                stat.tokens_out += t_in
                record("rejected", "decode_mismatch", t_in, t_in, ms)
                continue

            stat.accepted += 1
            stat.tokens_in_accepted += t_in
            stat.tokens_out += t_out
            record("accepted", "", t_in, t_out, ms)
            text = output
            accepted_by.append(spec.id)
            terminal_reached = terminal_reached or spec.terminal

        return text, accepted_by
