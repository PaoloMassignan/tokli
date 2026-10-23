"""Cache keepalive (SPEC 020, ADR 0016).

For a recently active Anthropic conversation with a one-hour prompt cache, Tokli repeats the last
forwarded request with ``max_tokens: 1`` shortly before the cache expires, so that the
developer's return after a pause reads the cache instead of writing it again (E12). Everything a
ping needs (the forwarded body and headers) is held in memory only, per kept conversation, and
dropped when the conversation stops being kept (KA-003, KA-010).
On by default (KA-001, S8l SCR-004).

All state lives on the server's event loop: the proxy calls ``begin`` and ``end`` from it, and
each kept conversation has one asyncio task that sleeps until its next ping (KA-005, KA-014).
A configuration change may arrive from a worker thread and is handed to the loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from tokli.app.api import request_view
from tokli.app.conversations import ConversationStore
from tokli.config.schema import KeepaliveSection
from tokli.domain.usage import Usage
from tokli.observability.ids import new_request_id
from tokli.observability.logs import REQUEST_LOGGER, log_fields
from tokli.observability.trace import Trace, TraceBuffer
from tokli.protocols.anthropic_usage import BodyUsageParser, StreamUsageParser, unavailable
from tokli.telemetry.records import RequestRecord
from tokli.telemetry.store import TelemetryStore
from tokli.upstream.forwarder import Upstream, UpstreamError

_LOG = logging.getLogger("tokli.keepalive")
_REQUESTS = logging.getLogger(REQUEST_LOGGER)
PROTOCOL = "anthropic_messages"
ENDPOINT = "/v1/messages"
MISSED_WRITE_SHARE = 0.05  # KA-007: a ping that writes more than this share missed the cache
Headers = list[tuple[str, str]]


@dataclass(frozen=True)
class ClientResult:
    """What a completed client request tells the keepalive (KA-002)."""

    status: int | None
    usage: Usage
    cache_ttl_s: float | None
    credential_kind: str
    body: bytes  # as forwarded, after compression (S8l D2)
    headers: Sequence[tuple[str, str]]  # as forwarded, after auth
    path: str
    model: str | None
    stream: bool


@dataclass
class _Kept:
    body: bytes
    headers: Headers
    path: str
    model: str | None
    stream: bool
    credential_kind: str
    ttl: float
    prefix: int
    client_at: float  # when the last client request was sent
    base: float  # the later of client_at and the last successful ping
    pinged: bool = False
    task: asyncio.Task[None] | None = field(default=None, repr=False)


def prefix_size(usage: Usage) -> int:
    """The cached prefix the provider reported: cache read plus cache write (SPEC 020)."""
    return (usage.cache_read or 0) + (usage.cache_write_5m or 0) + (usage.cache_write_1h or 0)


def ping_body(body: bytes) -> bytes:
    """KA-004: the held body with only `max_tokens` changed."""
    data = json.loads(body)
    thinking = data.get("thinking")
    budget = thinking.get("budget_tokens") if isinstance(thinking, dict) else None
    if isinstance(thinking, dict) and thinking.get("type") == "enabled" and isinstance(budget, int):
        data["max_tokens"] = budget + 1  # the API requires max_tokens above the budget
    else:
        data["max_tokens"] = 1
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Keepalive:
    def __init__(
        self,
        settings: KeepaliveSection | None = None,
        *,
        upstream: Upstream | None = None,
        conversations: ConversationStore | None = None,
        store: TelemetryStore | None = None,
        traces: TraceBuffer | None = None,
        margin_s: float = 60.0,
        usage_limit: int = 1024 * 1024,
        policy: str = "LOSSLESS_ONLY",
        config_hash: str = "",
    ) -> None:
        self.clock: Callable[[], float] = time.time  # wall clock: a sleep counts (KA-006)
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
        self._settings = settings or KeepaliveSection()
        self._upstream = upstream
        self._conversations = conversations
        self._store = store
        self._traces = traces
        self._margin_s = margin_s
        self._usage_limit = usage_limit
        self._policy = policy
        self._config_hash = config_hash
        self._kept: dict[str, _Kept] = {}
        self._in_flight: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None

    def __len__(self) -> int:
        return len(self._kept)

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    # -- the proxy's calls (on the event loop) --------------------------------------------------

    def begin(self, key: str) -> bool | None:
        """A client request of conversation ``key`` is about to be sent. Returns whether it is
        bridged (TC-024; ``None`` while the feature is off). No ping is sent while it is in
        flight (KA-012)."""
        self._bind()
        if not self._settings.enabled:
            return None
        self._in_flight[key] = self._in_flight.get(key, 0) + 1
        entry = self._kept.get(key)
        if entry is None:
            return False
        if entry.task is not None:
            entry.task.cancel()
            entry.task = None
        return entry.pinged and self.clock() - entry.client_at > entry.ttl + self._margin_s

    def end(self, key: str, result: ClientResult, sent_at: float | None) -> str | None:
        """The client request completed: keep its conversation or record why not (KA-002).
        Returns the trace value (`kept`, `ineligible(<why>)`), or ``None`` while off."""
        flying = self._in_flight.get(key, 0) - 1
        if flying > 0:
            self._in_flight[key] = flying
        else:
            self._in_flight.pop(key, None)
        if not self._settings.enabled:
            return None
        why = self._ineligible(result)
        if why is not None:
            reason = f"ineligible({why})"
            self._stop(key, reason)
            return reason
        now = sent_at if sent_at is not None else self.clock()
        assert result.cache_ttl_s is not None  # checked by _ineligible
        old = self._kept.pop(key, None)
        if old is not None and old.task is not None:
            old.task.cancel()
        entry = _Kept(
            body=result.body,
            headers=list(result.headers),
            path=result.path,
            model=result.model,
            stream=result.stream,
            credential_kind=result.credential_kind,
            ttl=result.cache_ttl_s,
            prefix=prefix_size(result.usage),
            client_at=now,
            base=now,
        )
        self._kept[key] = entry
        self._evict(keep=key)
        if key not in self._in_flight:
            self._schedule(key, entry)
        return "kept"

    def _ineligible(self, result: ClientResult) -> str | None:
        s = self._settings
        if result.status is None or not 200 <= result.status < 300:
            return "upstream_status"
        if result.usage.source != "provider":
            return "no_usage"
        if result.cache_ttl_s is None or result.cache_ttl_s < s.min_ttl_s:
            return "short_ttl"
        if prefix_size(result.usage) < s.min_prefix_tokens:
            return "too_small"
        if result.credential_kind == "oauth":
            return None if s.oauth else "oauth_not_enabled"
        if result.credential_kind != "api_key":
            return "credential_kind"
        return None

    # -- configuration and lifecycle ------------------------------------------------------------

    def configure(self, settings: KeepaliveSection, policy: str, config_hash: str) -> None:
        """A new configuration snapshot (KA-011). Safe to call from any thread."""
        loop = self._loop
        if loop is None or loop.is_closed() or self._loop_thread == threading.get_ident():
            self._apply(settings, policy, config_hash)
        else:
            loop.call_soon_threadsafe(self._apply, settings, policy, config_hash)

    def _apply(self, settings: KeepaliveSection, policy: str, config_hash: str) -> None:
        self._settings = settings
        self._policy, self._config_hash = policy, config_hash
        if not settings.enabled:
            self.stop_all("disabled")
        else:
            self._evict()

    def stop_all(self, reason: str) -> None:
        """Stops keeping every conversation (`disabled`, `shutdown`; KA-011)."""
        for key in list(self._kept):
            self._stop(key, reason)

    def _bind(self) -> None:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
            self._loop_thread = threading.get_ident()

    # -- keeping and stopping -------------------------------------------------------------------

    def _evict(self, keep: str | None = None) -> None:
        """KA-009: at most `max_conversations`; the oldest last client request goes first."""
        while len(self._kept) > self._settings.max_conversations:
            candidates = [k for k in self._kept if k != keep] or list(self._kept)
            oldest = min(candidates, key=lambda k: self._kept[k].client_at)
            self._stop(oldest, "evicted")

    def _stop(self, key: str, reason: str) -> None:
        """KA-010: drops everything held for ``key`` and logs the reason (never the key)."""
        entry = self._kept.pop(key, None)
        if entry is None:
            return
        task = entry.task
        if task is not None and task is not _current_task():
            task.cancel()
        log_fields(_LOG, logging.INFO, "keepalive stopped", event="keepalive_stop", reason=reason)

    def _schedule(self, key: str, entry: _Kept) -> None:
        entry.task = asyncio.get_running_loop().create_task(self._run(key, entry))

    async def _run(self, key: str, entry: _Kept) -> None:
        while self._kept.get(key) is entry:
            s = self._settings
            due = entry.base + entry.ttl - s.lead_s
            if due > entry.client_at + s.horizon_s:  # KA-005
                self._stop(key, "horizon")
                return
            await self.sleep(max(0.0, due - self.clock()))
            if self._kept.get(key) is not entry or key in self._in_flight:
                return
            if self.clock() > entry.base + entry.ttl:  # KA-006: the cache is probably gone
                self._stop(key, "expired")
                return
            reason = await self._ping(key, entry)
            if reason is not None:
                self._stop(key, reason)
                return

    # -- one ping -------------------------------------------------------------------------------

    async def _ping(self, key: str, entry: _Kept) -> str | None:
        """Sends one ping and records it (TC-023, OB-014). Returns the reason it stops the
        conversation, or ``None`` when the conversation stays kept."""
        assert self._upstream is not None
        started = time.perf_counter()
        rid = new_request_id()
        trace = Trace(rid, started)
        ts_start = _iso()
        sent = self.clock()
        payload = ping_body(entry.body)
        trace.span(
            "keepalive",
            started,
            time.perf_counter(),
            since_client_s=round(sent - entry.client_at),
            prefix_tokens=entry.prefix,
            cache_ttl_s=round(entry.ttl),
        )
        status: int | None = None
        error: str | None = None
        usage = unavailable("upstream_status")
        upstream_started = time.perf_counter()
        headers_at: float | None = None
        try:
            response = await self._upstream.open("POST", entry.path, "", entry.headers, payload)
        except UpstreamError as exc:
            error = exc.kind
        else:
            headers_at = time.perf_counter()
            status = response.status_code
            parser = self._parser(response)
            try:
                async for chunk in response.aiter_raw():  # read only for usage (KA-015)
                    if parser is not None:
                        parser.feed(chunk)
                if parser is not None:
                    usage = parser.result(disconnected=False)
            except httpx.HTTPError as exc:
                error = (
                    "upstream_timeout"
                    if isinstance(exc, httpx.TimeoutException)
                    else "upstream_unreachable"
                )
                if parser is not None:
                    usage = parser.result(disconnected=True)
            finally:
                await response.aclose()
        done = time.perf_counter()
        trace.span(
            "upstream",
            upstream_started,
            done,
            status="error" if error else "ok",
            status_code=status,
            **({"error": error} if error else {}),
        )
        trace.span("usage", done, done, status=usage.source, **_categories(usage))

        reason: str | None
        if error is not None or status is None:
            reason = "upstream_error"
        elif status in (401, 403):
            reason = "auth_rejected"
        elif not 200 <= status < 300 or usage.source == "unavailable":
            reason = "upstream_error"
        elif (usage.cache_write_5m or 0) + (usage.cache_write_1h or 0) > (
            MISSED_WRITE_SHARE * entry.prefix
        ):
            reason = "cache_missed"
        else:  # KA-007: a successful ping
            reason = None
            entry.base, entry.pinged = sent, True
            if self._conversations is not None:
                self._conversations.touch(key, sent)  # KA-013, PR-021
            s = self._settings
            if entry.base + entry.ttl - s.lead_s > entry.client_at + s.horizon_s:
                reason = "horizon"  # this was the last ping (KA-005)
        if reason is not None:
            trace.decide("keepalive", reason)
        ended = time.perf_counter()
        record = RequestRecord(
            request_id=rid,
            ts_start=ts_start,
            ts_end=_iso(),
            provider="anthropic",
            protocol=PROTOCOL,
            endpoint=ENDPOINT,
            model=entry.model,
            stream=entry.stream,
            auth_mode="passthrough",
            credential_kind=entry.credential_kind,
            policy=self._policy,
            config_hash=self._config_hash,
            outcome="keepalive",
            passthrough_reason=None,
            segments_total=0,
            segments_mutable=0,
            segments_changed=0,
            tokenizer_id=None,
            est_original_tokens=None,
            est_forwarded_tokens=None,
            status_code=status,
            ms_parse=None,
            ms_pipeline=None,
            ms_render=None,
            ms_upstream_ttfb=(
                (headers_at - upstream_started) * 1000 if headers_at is not None else None
            ),
            ms_upstream_total=(done - upstream_started) * 1000,
            ms_tokli_overhead=None,
            ms_total=(ended - started) * 1000,
            error_code=f"tokli_{error}" if error else None,
            usage_source=usage.source,
            usage_input=usage.input,
            usage_cache_read=usage.cache_read,
            usage_cache_write_5m=usage.cache_write_5m,
            usage_cache_write_1h=usage.cache_write_1h,
            usage_output=usage.output,
            stop_reason=usage.stop_reason,
            keepalive_stop_reason=reason,
            cache_ttl_s=entry.ttl,
        )
        if self._store is not None:
            self._store.submit(record, [])
        if self._traces is not None:
            self._traces.add(rid, request_view(record, [], trace.to_dict()))
        log_fields(
            _REQUESTS,
            logging.INFO,
            "request",
            event="request",
            request_id=rid,
            provider="anthropic",
            model=entry.model,
            stream=entry.stream,
            outcome="keepalive",
            reason=reason,
            status=status,
            credential_kind=entry.credential_kind,
            tokens={
                "usage": (
                    {"source": usage.source, "method": "exact", **_categories(usage)}
                    if usage.source != "unavailable"
                    else {"value": None, "reason": usage.reason or "usage_unavailable"}
                )
            },
        )
        return reason

    def _parser(self, response: httpx.Response) -> StreamUsageParser | BodyUsageParser | None:
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        if response.status_code >= 400 or encoding not in ("", "identity"):
            return None
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            return StreamUsageParser(self._usage_limit)
        return BodyUsageParser(self._usage_limit)


def _categories(usage: Usage) -> dict[str, Any]:
    return {
        "input": usage.input,
        "cache_read": usage.cache_read,
        "cache_write_5m": usage.cache_write_5m,
        "cache_write_1h": usage.cache_write_1h,
        "output": usage.output,
    }


def _current_task() -> asyncio.Task[Any] | None:
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None
