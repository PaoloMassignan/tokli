"""The proxy flow for ``/anthropic/*`` (SPEC 002, 003, 006; ARCH §6).

route → parse → pipeline → render → auth (headers only) → upstream → streamed relay. Every
failure before the upstream call falls back to forwarding the original bytes (PX-010); only an
unreachable upstream produces a Tokli error response (PX-008). Parse, pipeline and render run
on a worker thread, so one request's transformation never stalls the relay of others (PX-015,
ADR 0011).

For the transformable endpoint the relay also feeds a passive usage parser, after each chunk has
been passed on (AN-006), and a worker thread estimates the whole request while the upstream
answers (TM-004, I1). The record is completed when both are done, never delaying the client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import anyio
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tokli.app import measurement
from tokli.app.api import CompressionReport, compression_report, compressor_summary
from tokli.app.bootstrap import Services
from tokli.app.request_record import Observed, now_iso, record_request, usage_categories
from tokli.app.runtime import Runtime
from tokli.auth.passthrough import credential_kind, forward_request_headers, header_names
from tokli.domain.models import CanonicalRequest
from tokli.domain.stage import StageContext
from tokli.domain.usage import Usage
from tokli.observability.ids import new_request_id
from tokli.observability.logs import log_fields
from tokli.observability.trace import Trace
from tokli.protocols.anthropic_messages import PROTOCOL, ParseError, parse, render
from tokli.protocols.anthropic_usage import BodyUsageParser, StreamUsageParser, unavailable
from tokli.upstream.forwarder import UpstreamError, response_headers

PREFIX = "/anthropic"
PROVIDER = "anthropic"
_ERROR_BODY_LIMIT = 64 * 1024
_WARN_INTERVAL_S = 60.0  # calibration outliers: at most one WARNING per minute (TM-009)


def canonical_endpoint(method: str, rest: str) -> str | None:
    """The known transformable endpoint for ``rest``, if any (trailing slash and case ignored,
    a missing ``/v1`` added)."""
    if method != "POST":
        return None
    path = "/" + rest.strip("/").lower()
    return "/v1/messages" if path in ("/v1/messages", "/messages") else None


@dataclass
class _State:
    """What the proxy learns about one request, turned into a record at the end."""

    request_id: str
    started: float
    ts_start: str
    endpoint: str
    protocol: str | None = None
    model: str | None = None
    stream: bool = False
    outcome: str = "verbatim_route"
    reason: str | None = None
    segments_total: int = 0
    segments_mutable: int = 0
    segments_changed: int = 0
    tokenizer_id: str | None = None
    engine: CompressionReport | None = None
    credential_kind: str = "none"
    ms_parse: float | None = None
    ms_pipeline: float | None = None
    ms_render: float | None = None
    upstream_started: float | None = None
    upstream_headers_at: float | None = None
    upstream_done: float | None = None
    status_code: int | None = None
    error_code: str | None = None
    error_details: dict[str, str] = field(default_factory=dict)
    header_names: tuple[str, ...] = ()
    request: CanonicalRequest | None = None
    counter: measurement.TokenCounter | None = None
    parser: StreamUsageParser | BodyUsageParser | None = None
    usage: Usage = field(default_factory=lambda: Usage(source="unavailable"))
    ms_usage: float = 0.0
    estimate: asyncio.Future[measurement.RequestEstimate] | None = None
    services: Services | None = None  # the snapshot this request started with (CF-005)


class ProxyHandler:
    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        # Read once: these keys are not UI-editable (CF-009), so a PATCH never changes them.
        settings = runtime.current().config.settings
        self._max_bytes = settings.limits.max_transform_bytes
        self._usage_limit = settings.limits.usage_parser_buffer
        self._response_header = settings.observability.response_header
        self._pending: set[asyncio.Task[None]] = set()
        self._last_outlier_warning = 0.0

    # -- entry point ---------------------------------------------------------------------------

    async def handle(self, request: Request) -> Response:
        started = time.perf_counter()
        rid = new_request_id()
        trace = Trace(rid, started)
        raw_path = request.scope.get("raw_path") or request.url.path.encode("utf-8")
        rest = raw_path[len(PREFIX) :].decode("latin-1") or "/"
        query = request.scope.get("query_string", b"").decode("latin-1")
        endpoint = canonical_endpoint(request.method, rest)
        state = _State(rid, started, now_iso(), endpoint or rest.split("?")[0])
        services = state.services = self._runtime.current()
        trace.span(
            "route", started, time.perf_counter(), provider=PROVIDER, endpoint=state.endpoint
        )
        trace.decide("route", "known_endpoint" if endpoint else "verbatim_path")

        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in request.headers.raw]
        state.header_names = tuple(header_names(headers))
        trace.attrs["header_names"] = list(state.header_names)
        body = await request.body()

        forward_body, forward_path = body, rest
        if endpoint is not None:
            forward_path = endpoint
            forward_body = await anyio.to_thread.run_sync(
                self._transform, body, headers, trace, state
            )

        auth_started = time.perf_counter()
        upstream_headers = forward_request_headers(headers)
        if endpoint is not None:  # PX-014: plain-text responses where usage is parsed
            upstream_headers = [
                (name, value)
                for name, value in upstream_headers
                if name.lower() != "accept-encoding"
            ]
            upstream_headers.append(("accept-encoding", "identity"))
        state.credential_kind = credential_kind(headers)
        trace.span(
            "auth",
            auth_started,
            time.perf_counter(),
            mode="passthrough",
            credential_kind=state.credential_kind,
        )

        state.upstream_started = time.perf_counter()
        try:
            upstream = await services.upstream.open(
                request.method, forward_path, query, upstream_headers, forward_body
            )
        except UpstreamError as exc:
            return self._upstream_failure(exc, trace, state)
        state.upstream_headers_at = time.perf_counter()
        state.status_code = upstream.status_code
        trace.attrs["upstream_request_id"] = upstream.headers.get(
            "request-id"
        ) or upstream.headers.get("x-request-id")
        if upstream.status_code >= 400:
            trace.decide("upstream", f"upstream_status({upstream.status_code})")

        streaming = state.stream or upstream.headers.get("content-type", "").startswith(
            "text/event-stream"
        )
        if endpoint is not None:
            self._start_measurement(upstream, state)
        response = StreamingResponse(
            self._relay(upstream, trace, state), status_code=upstream.status_code
        )
        relayed = response_headers(upstream, streaming=streaming)
        if self._response_header:
            relayed.append(("x-tokli-request-id", rid))
        response.raw_headers = [
            (name.lower().encode("latin-1"), value.encode("latin-1")) for name, value in relayed
        ]
        return response

    # -- request transformation ----------------------------------------------------------------

    def _passthrough(self, trace: Trace, state: _State, reason: str) -> None:
        state.outcome = "passthrough"
        state.reason = reason
        trace.decide("passthrough", reason)

    def _transform(
        self, body: bytes, headers: list[tuple[str, str]], trace: Trace, state: _State
    ) -> bytes:
        services = state.services
        assert services is not None  # set by handle()
        state.protocol = PROTOCOL
        if any(name.lower() == "content-encoding" for name, _ in headers):
            self._passthrough(trace, state, "content_encoding")
            return body
        if len(body) > self._max_bytes:
            self._passthrough(trace, state, "too_large")
            return body

        parse_started = time.perf_counter()
        try:
            request = parse(body, mutable_kinds=services.mutable_kinds)
        except ParseError:
            trace.span("parse", parse_started, time.perf_counter(), status="error")
            self._passthrough(trace, state, "parse_error")
            return body
        parse_done = time.perf_counter()
        state.ms_parse = (parse_done - parse_started) * 1000
        state.model, state.stream = request.model, request.stream
        state.segments_total = len(request.segments)
        state.segments_mutable = sum(1 for s in request.segments if s.mutable)
        trace.span(
            "parse",
            parse_started,
            parse_done,
            segments=state.segments_total,
            mutable=state.segments_mutable,
            bytes=len(body),
        )
        counter = services.selector.select(request.model)
        state.tokenizer_id = counter.tokenizer_id
        state.request, state.counter = request, counter
        if state.segments_mutable == 0:
            self._passthrough(trace, state, "no_mutable_segments")
            return body

        pipeline_started = time.perf_counter()
        try:
            result = services.pipeline.run(request, StageContext(request_id=state.request_id))
        except Exception:  # fail to pass-through (PX-010)
            trace.span("pipeline", pipeline_started, time.perf_counter(), status="error")
            self._passthrough(trace, state, "pipeline_error")
            return body
        state.ms_pipeline = (time.perf_counter() - pipeline_started) * 1000
        cursor = pipeline_started
        state.engine = compression_report(result.reports)
        for outcome in result.outcomes:
            attrs: dict[str, Any] = {"reason": outcome.reason} if outcome.reason else {}
            if outcome.stage_id == "transform.compression" and state.engine is not None:
                attrs["compressors"] = compressor_summary(state.engine)
            trace.span(
                outcome.stage_id, cursor, cursor + outcome.ms / 1000, status=outcome.status, **attrs
            )
            cursor += outcome.ms / 1000
            if outcome.status != "ok":
                trace.decide("stage", outcome.reason)

        if not result.patches:
            applicable = state.engine is not None and state.engine.any_applicable
            self._passthrough(trace, state, "no_gain" if applicable else "no_applicable_compressor")
            return body

        render_started = time.perf_counter()
        try:
            rendered = render(request, result.patches)
        except Exception:  # fail to pass-through (PX-010)
            trace.span("render", render_started, time.perf_counter(), status="error")
            self._passthrough(trace, state, "render_error")
            return body
        render_done = time.perf_counter()
        state.ms_render = (render_done - render_started) * 1000
        state.segments_changed = len(result.patches)
        state.outcome = "compressed"
        trace.span(
            "render",
            render_started,
            render_done,
            patches=len(result.patches),
            bytes_before=len(body),
            bytes_after=len(rendered),
        )
        return rendered

    # -- relay and completion ------------------------------------------------------------------

    async def _relay(self, upstream: httpx.Response, trace: Trace, state: _State):  # type: ignore[no-untyped-def]
        completed = False
        error_body = bytearray()
        try:
            async for chunk in upstream.aiter_raw():
                if upstream.status_code >= 400 and len(error_body) < _ERROR_BODY_LIMIT:
                    error_body.extend(chunk[: _ERROR_BODY_LIMIT - len(error_body)])
                yield chunk
                if state.parser is not None:  # after the chunk was passed on (AN-006)
                    parse_started = time.perf_counter()
                    state.parser.feed(chunk)
                    state.ms_usage += (time.perf_counter() - parse_started) * 1000
            completed = True
        except httpx.HTTPError as exc:
            state.error_code = (
                "upstream_timeout" if isinstance(exc, httpx.TimeoutException) else "upstream_error"
            )
            trace.decide(
                "upstream",
                "upstream_timeout"
                if isinstance(exc, httpx.TimeoutException)
                else "upstream_unreachable",
            )
        finally:
            with anyio.CancelScope(shield=True):
                await upstream.aclose()
            state.upstream_done = time.perf_counter()
            if not completed and state.error_code is None:
                trace.decide("upstream", "client_disconnected")
                state.error_code = "client_disconnected"
            if upstream.status_code >= 400:
                state.error_details = _error_fields(
                    bytes(error_body), upstream.headers.get("content-encoding")
                )
            if state.parser is not None:
                state.usage = state.parser.result(disconnected=not completed)
                state.parser = None
            self._finish(trace, state)

    def _upstream_failure(self, exc: UpstreamError, trace: Trace, state: _State) -> Response:
        state.upstream_done = time.perf_counter()
        assert state.upstream_started is not None
        trace.span(
            "upstream", state.upstream_started, state.upstream_done, status="error", error=exc.kind
        )
        trace.decide("upstream", exc.kind)
        status = 504 if exc.kind == "upstream_timeout" else 502
        state.status_code = status
        state.error_code = f"tokli_{exc.kind}"
        if state.protocol is not None:
            state.usage = unavailable("upstream_status")
        self._finish(trace, state)
        headers = {"x-tokli-request-id": state.request_id} if self._response_header else {}
        return JSONResponse(
            {
                "error": {
                    "type": f"tokli_{exc.kind}",
                    "message": f"Tokli could not complete the upstream request ({exc.kind})",
                    "source": "tokli",
                    "request_id": state.request_id,
                }
            },
            status_code=status,
            headers=headers,
        )

    def _start_measurement(self, upstream: httpx.Response, state: _State) -> None:
        """Chooses the usage parser (AN-005…AN-007, PX-014) and starts the whole-request
        estimate in a worker thread (TM-004, I1)."""
        encoding = upstream.headers.get("content-encoding", "identity").strip().lower()
        if upstream.status_code >= 400:
            state.usage = unavailable("upstream_status")
        elif encoding not in ("", "identity"):
            state.usage = unavailable("content_encoding")
        elif upstream.headers.get("content-type", "").startswith("text/event-stream"):
            state.parser = StreamUsageParser(self._usage_limit)
        else:
            state.parser = BodyUsageParser(self._usage_limit)
        if state.request is not None and state.counter is not None and upstream.status_code < 400:
            engine = state.engine
            saved = engine.est_original_tokens - engine.est_forwarded_tokens if engine else 0
            state.estimate = asyncio.get_running_loop().run_in_executor(
                None, measurement.whole_request_estimates, state.request, state.counter, saved
            )

    def _finish(self, trace: Trace, state: _State) -> None:
        """Closes the request's timings now; completes the record when the whole-request
        estimate is ready, so the end of the response is never held back."""
        ended = time.perf_counter()
        estimate = state.estimate
        if estimate is None or estimate.done():
            self._complete(trace, state, ended)
            return

        async def complete_later() -> None:
            try:
                await asyncio.wait([estimate])
            finally:
                self._complete(trace, state, ended)

        task = asyncio.get_running_loop().create_task(complete_later())
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _complete(self, trace: Trace, state: _State, ended: float) -> None:
        services = state.services
        assert services is not None  # set by handle()
        upstream_start = state.upstream_started or ended
        upstream_done = state.upstream_done or ended
        if state.upstream_headers_at is not None:
            trace.span(
                "upstream",
                upstream_start,
                upstream_done,
                status_code=state.status_code,
                ttfb_ms=(state.upstream_headers_at - upstream_start) * 1000,
            )
        usage = state.usage
        transformable = state.protocol is not None
        if transformable:
            if usage.reason is not None:
                trace.decide("usage", usage.reason)
            trace.span(
                "usage",
                ended - state.ms_usage / 1000,
                ended,
                status=usage.source,
                source=usage.source,
                **({"reason": usage.reason} if usage.reason else {}),
                **usage_categories(usage),
                events=dict(usage.events),
                delta_usage_fields=list(usage.delta_fields),
            )
        else:
            trace.span("usage", ended, ended, status="unavailable")

        estimate: measurement.RequestEstimate | None = None
        future = state.estimate
        if (
            future is not None
            and future.done()
            and not future.cancelled()
            and future.exception() is None
        ):
            estimate = future.result()
        engine = state.engine
        saved: int | None
        if engine is not None:
            saved = engine.est_original_tokens - engine.est_forwarded_tokens
        else:
            saved = 0 if state.request is not None else None
        calibration = measurement.calibrate_request(usage, estimate, saved)
        if transformable:
            self._record_calibration(trace, calibration, estimate)

        observed = Observed(
            request_id=state.request_id,
            ts_start=state.ts_start,
            provider=PROVIDER,
            protocol=state.protocol,
            endpoint=state.endpoint,
            model=state.model,
            stream=state.stream,
            auth_mode="passthrough",
            credential_kind=state.credential_kind,
            outcome=state.outcome,
            reason=state.reason,
            segments_total=state.segments_total,
            segments_mutable=state.segments_mutable,
            segments_changed=state.segments_changed,
            tokenizer_id=state.tokenizer_id,
            status_code=state.status_code,
            ms_parse=state.ms_parse,
            ms_pipeline=state.ms_pipeline,
            ms_render=state.ms_render,
            ms_upstream_ttfb=(
                (state.upstream_headers_at - upstream_start) * 1000
                if state.upstream_headers_at is not None
                else None
            ),
            ms_upstream_total=(upstream_done - upstream_start) * 1000,
            ms_total=(ended - state.started) * 1000,
            error_code=state.error_code,
            header_names=state.header_names,
            usage=usage,
            error_details=state.error_details,
        )
        record_request(services, observed, engine, estimate, calibration, trace.to_dict())

    def _record_calibration(
        self,
        trace: Trace,
        calibration: measurement.Calibration,
        estimate: measurement.RequestEstimate | None,
    ) -> None:
        """Trace, health window and rate-limited warning for calibration (TM-009, OB-011)."""
        if calibration.reason is not None:
            trace.decide("calibration", calibration.reason)
        now = time.perf_counter()
        trace.span(
            "calibrate",
            estimate.started if estimate else now,
            estimate.ended if estimate else now,
            status=calibration.status,
            k=calibration.k,
            estimate=estimate.forwarded if estimate else None,
            saving=calibration.saving,
            method=calibration.method,
        )
        if calibration.status == "unavailable":
            return
        outlier = calibration.status == "outlier"
        self._runtime.current().calibration.add(outlier=outlier)
        moment = time.monotonic()
        last = self._last_outlier_warning
        if outlier and (last == 0.0 or moment - last >= _WARN_INTERVAL_S):
            self._last_outlier_warning = moment
            log_fields(
                logging.getLogger("tokli.calibration"),
                logging.WARNING,
                "calibration outlier",
                event="calibration_outlier",
                k=round(calibration.k or 0.0, 4),
                range=list(measurement.OUTLIER_RANGE),
            )


def _error_fields(body: bytes, encoding: str | None) -> dict[str, str]:
    """Provider error type and message only (OB-006); the raw body is never logged."""
    if encoding and encoding.lower() != "identity":
        return {"type": "unknown"}
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return {"type": "unparsed"}
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return {"type": "unparsed"}
    return {
        "type": str(error.get("type", "unknown"))[:100],
        "message": str(error.get("message", ""))[:500],
    }
