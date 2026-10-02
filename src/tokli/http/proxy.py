"""The proxy flow for ``/anthropic/*`` (SPEC 002, 003, 006; ARCH §6).

route → parse → pipeline → render → auth (headers only) → upstream → streamed relay. Every
failure before the upstream call falls back to forwarding the original bytes (PX-010); only an
unreachable upstream produces a Tokli error response (PX-008).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import anyio
import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tokli.app.api import (
    POLICY,
    compression_report,
    compressor_summary,
    request_view,
    stats_records,
)
from tokli.app.bootstrap import Services
from tokli.auth.passthrough import credential_kind, forward_request_headers, header_names
from tokli.domain.stage import StageContext
from tokli.observability.ids import new_request_id
from tokli.observability.logs import REQUEST_LOGGER, log_fields
from tokli.observability.trace import Trace
from tokli.protocols.anthropic_messages import PROTOCOL, ParseError, parse, render
from tokli.telemetry.records import RequestRecord
from tokli.upstream.forwarder import UpstreamError, response_headers

PREFIX = "/anthropic"
PROVIDER = "anthropic"
_LOG = logging.getLogger(REQUEST_LOGGER)
_ERROR_BODY_LIMIT = 64 * 1024


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


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
    engine: Any = None  # the compression report (tokli.app.api.compression_report)
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


class ProxyHandler:
    def __init__(self, services: Services) -> None:
        self._services = services
        settings = services.config.settings
        self._max_bytes = settings.limits.max_transform_bytes
        self._response_header = settings.observability.response_header

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
        trace.span(
            "route", started, time.perf_counter(), provider=PROVIDER, endpoint=state.endpoint
        )
        trace.decide("route", "known_endpoint" if endpoint else "verbatim_path")

        headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in request.headers.raw]
        trace.attrs["header_names"] = header_names(headers)
        body = await request.body()

        forward_body, forward_path = body, rest
        if endpoint is not None:
            forward_path = endpoint
            forward_body = self._transform(body, headers, trace, state)

        auth_started = time.perf_counter()
        upstream_headers = forward_request_headers(headers)
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
            upstream = await self._services.upstream.open(
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
        services = self._services
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
        state.tokenizer_id = getattr(counter, "tokenizer_id", None)
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

    def _finish(self, trace: Trace, state: _State) -> None:
        services = self._services
        ended = time.perf_counter()
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
        trace.span("usage", ended, ended, status="unavailable")
        ms_total = (ended - state.started) * 1000
        ms_upstream_total = (upstream_done - upstream_start) * 1000
        engine = state.engine
        record = RequestRecord(
            request_id=state.request_id,
            ts_start=state.ts_start,
            ts_end=now_iso(),
            provider=PROVIDER,
            protocol=state.protocol,
            endpoint=state.endpoint,
            model=state.model,
            stream=state.stream,
            auth_mode="passthrough",
            credential_kind=state.credential_kind,
            policy=POLICY,
            config_hash=services.config.config_hash,
            outcome=state.outcome,
            passthrough_reason=state.reason,
            segments_total=state.segments_total,
            segments_mutable=state.segments_mutable,
            segments_changed=state.segments_changed,
            tokenizer_id=state.tokenizer_id,
            est_original_tokens=engine.est_original_tokens if engine else None,
            est_forwarded_tokens=engine.est_forwarded_tokens if engine else None,
            status_code=state.status_code,
            ms_parse=state.ms_parse,
            ms_pipeline=state.ms_pipeline,
            ms_render=state.ms_render,
            ms_upstream_ttfb=(
                (state.upstream_headers_at - upstream_start) * 1000
                if state.upstream_headers_at is not None
                else None
            ),
            ms_upstream_total=ms_upstream_total,
            ms_tokli_overhead=max(0.0, ms_total - ms_upstream_total),
            ms_total=ms_total,
            error_code=state.error_code,
        )
        stats = stats_records(state.request_id, engine.stats if engine else ())
        if services.store is not None:
            services.store.submit(record, stats)
        services.traces.add(state.request_id, request_view(record, stats, trace.to_dict()))
        saved = (
            record.est_original_tokens - record.est_forwarded_tokens
            if record.est_original_tokens is not None and record.est_forwarded_tokens is not None
            else None
        )
        log_fields(
            _LOG,
            logging.INFO,
            "request",
            event="request",
            request_id=state.request_id,
            provider=PROVIDER,
            model=state.model,
            stream=state.stream,
            outcome=state.outcome,
            reason=state.reason,
            status=state.status_code,
            credential_kind=state.credential_kind,
            overhead_ms=round(record.ms_tokli_overhead or 0.0, 3),
            tokens={
                "original": {"value": record.est_original_tokens, "method": "estimate"},
                "forwarded": {"value": record.est_forwarded_tokens, "method": "estimate"},
                "saved": {"value": saved, "method": "estimate"},
            },
            **({"upstream_error": state.error_details} if state.error_details else {}),
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
