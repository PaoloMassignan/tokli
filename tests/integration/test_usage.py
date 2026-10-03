"""S2 end to end: PX-014, usage from responses and streams (AN-005…AN-010), calibration (TM-003…
TM-005, TM-009), the calibration health check (OB-011) and persisted header names (OB-012)."""

from __future__ import annotations

import asyncio
import gzip
import json
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tests.integration.servers import FakeUpstream, Tokli

ROOT = Path(__file__).resolve().parents[1] / "compat" / "fixtures"
REQUESTS = ROOT / "anthropic_messages"
RESPONSES = ROOT / "anthropic_responses"
KEY = "sk-ant-api03-TOKLI-CANARY-KEY-SECRET"
HEADERS = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
Start = Callable[..., Tokli]


def request_body(name: str = "tool_use_and_results", *, stream: bool = False) -> bytes:
    data = json.loads((REQUESTS / f"{name}.json").read_bytes())
    return json.dumps({**data, "stream": stream}).encode()


def events(name: str) -> list[bytes]:
    """The fixture's SSE events, each ending with its blank line."""
    raw = (RESPONSES / name).read_bytes()
    return [part + b"\n\n" for part in raw.split(b"\n\n") if part.strip()]


def sse_responder(chunks: list[bytes]) -> Callable[[Request], Any]:
    async def responder(request: Request) -> Response:
        async def gen() -> AsyncIterator[bytes]:
            for chunk in chunks:
                yield chunk

        return StreamingResponse(gen(), media_type="text/event-stream")

    return responder


def usage_responder(usage: dict[str, int]) -> Callable[[Request], Any]:
    async def responder(request: Request) -> Response:
        return JSONResponse({"id": "msg_test", "type": "message", "content": [], "usage": usage})

    return responder


def send(tokli: Tokli, content: bytes | None = None, **headers: str) -> dict[str, Any]:
    response = httpx.post(
        tokli.url + "/anthropic/v1/messages",
        content=content if content is not None else request_body(),
        headers={**HEADERS, **headers},
        timeout=10,
    )
    return tokli.wait_trace(response.headers["x-tokli-request-id"])


def decisions(view: dict[str, Any]) -> list[str]:
    return [d["reason"] for d in view["trace"]["decisions"]]


def span(view: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in view["trace"]["spans"] if s["name"] == name)


# -- PX-014 ------------------------------------------------------------------------------------


def test_transformable_request_asks_identity_encoding(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    send(t, **{"accept-encoding": "gzip, br"})
    send(t, b"{not json", **{"accept-encoding": "gzip"})  # passed through, same endpoint
    for received in upstream.received:
        values = [v for k, v in received.headers if k.lower() == "accept-encoding"]
        assert values == ["identity"]


def test_verbatim_route_keeps_client_accept_encoding(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    httpx.post(
        t.url + "/anthropic/v1/messages/count_tokens",
        content=request_body(),
        headers={**HEADERS, "accept-encoding": "gzip"},
        timeout=10,
    )
    values = [v for k, v in upstream.received[-1].headers if k.lower() == "accept-encoding"]
    assert values == ["gzip"]


# -- usage, non-streaming and streaming --------------------------------------------------------


def test_anthropic_usage_non_stream_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    upstream.responder = usage_responder(
        json.loads((RESPONSES / "non_stream.json").read_bytes())["usage"]
    )
    record = send(tokli())["record"]
    assert record["usage_source"] == "provider"
    assert record["usage_input"] == {"value": 12, "method": "exact"}
    assert record["usage_cache_read"] == {"value": 4000, "method": "exact"}
    assert record["usage_cache_write_5m"] == {"value": 0, "method": "exact"}
    assert record["usage_cache_write_1h"] == {"value": 500, "method": "exact"}
    assert record["usage_output"] == {"value": 7, "method": "exact"}
    forwarded = record["est_request_tokens_forwarded"]
    assert forwarded["method"] == "estimate" and forwarded["value"] > 0
    assert record["calibration_k"] == pytest.approx(4512 / forwarded["value"])


def test_anthropic_usage_stream_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    upstream.responder = sse_responder(events("stream_basic.sse"))
    view = send(tokli(), request_body(stream=True))
    record = view["record"]
    assert record["usage_source"] == "provider"
    assert record["usage_input"]["value"] == 25 and record["usage_output"]["value"] == 15
    assert record["usage_cache_write_1h"]["value"] == 200
    usage = span(view, "usage")
    assert usage["attrs"]["source"] == "provider"
    assert usage["attrs"]["events"]["message_delta"] == 1


def test_anthropic_usage_stream_with_error_event_end_to_end(
    tokli: Start, upstream: FakeUpstream
) -> None:
    upstream.responder = sse_responder(events("stream_error_event.sse"))
    record = send(tokli(), request_body(stream=True))["record"]
    assert record["usage_source"] == "provider_partial"
    assert record["usage_input"]["value"] == 25
    assert record["usage_output"] == {"value": 1, "method": "exact", "partial": True}
    assert record["calibration_k"] is not None  # input categories are complete


def test_stream_causal_relay_with_usage_tee(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-AN-4: the relay stays unbuffered with the usage tee active (causal test, AC-PX-3)."""
    chunks = events("stream_basic.sse")
    received = [threading.Event() for _ in chunks]
    stalled: list[int] = []

    async def responder(request: Request) -> Response:
        async def gen() -> AsyncIterator[bytes]:
            for i, chunk in enumerate(chunks):
                yield chunk
                if i + 1 < len(chunks) and not await asyncio.to_thread(received[i].wait, 5):
                    stalled.append(i)
                    return

        return StreamingResponse(gen(), media_type="text/event-stream")

    upstream.responder = responder
    t = tokli()
    got = b""
    with httpx.stream(
        "POST",
        t.url + "/anthropic/v1/messages",
        content=request_body(stream=True),
        headers=HEADERS,
        timeout=15,
    ) as response:
        for piece in response.iter_raw():
            got += piece
            for i in range(len(chunks)):
                if got.startswith(b"".join(chunks[: i + 1])):
                    received[i].set()
        rid = response.headers["x-tokli-request-id"]
    assert stalled == []
    assert got == b"".join(chunks)
    assert t.wait_trace(rid)["record"]["usage_source"] == "provider"


def test_usage_unavailable_reasons_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-AN-6 (end-to-end causes): upstream error, encoded body, client disconnect."""
    t = tokli()

    async def rate_limited(request: Request) -> Response:
        return JSONResponse({"type": "error", "error": {"type": "rate_limit_error"}}, 429)

    upstream.responder = rate_limited
    view = send(t)
    assert view["record"]["usage_source"] == "unavailable"
    assert "usage_unavailable(upstream_status)" in decisions(view)

    async def encoded(request: Request) -> Response:
        body = gzip.compress((RESPONSES / "non_stream.json").read_bytes())
        return Response(body, headers={"content-encoding": "gzip"}, media_type="application/json")

    upstream.responder = encoded
    view = send(t)
    assert "usage_unavailable(content_encoding)" in decisions(view)

    # The upstream never ends on its own, so only the client's disconnect can end the relay.
    # (A gate released after the disconnect let the upstream finish first on fast runners: then
    # the stream really was complete and `no_usage` was the right answer, CI 2026-10-02.)
    async def slow(request: Request) -> Response:
        async def gen() -> AsyncIterator[bytes]:
            for _ in range(200):
                yield b"event: ping\ndata: {}\n\n"
                await asyncio.sleep(0.05)

        return StreamingResponse(gen(), media_type="text/event-stream")

    upstream.responder = slow
    with httpx.stream(
        "POST",
        t.url + "/anthropic/v1/messages",
        content=request_body(stream=True),
        headers=HEADERS,
        timeout=10,
    ) as response:
        next(response.iter_raw())
        rid = response.headers["x-tokli-request-id"]
    view = t.wait_trace(rid)
    assert "usage_unavailable(client_disconnected)" in decisions(view)


# -- calibration -------------------------------------------------------------------------------


def test_calibrated_saving_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """TM-004 / TM-005: a request whose provider input is 1.1 x Tokli's estimate gets a
    calibrated saving of 1.1 x the estimated saving, labelled everywhere."""
    t = tokli()
    upstream.responder = usage_responder({"input_tokens": 1, "output_tokens": 1})
    first = send(t)["record"]
    estimate = first["est_request_tokens_forwarded"]["value"]
    saved = first["est_original_tokens"]["value"] - first["est_forwarded_tokens"]["value"]
    assert saved > 0

    exact = round(estimate * 1.1)
    upstream.responder = usage_responder({"input_tokens": exact, "output_tokens": 3})
    view = send(t)
    record = view["record"]
    assert record["calibration_k"] == pytest.approx(exact / estimate)
    assert record["saving"] == {"value": round(saved * exact / estimate), "method": "calibrated"}
    original = record["request_tokens_original"]
    assert original["method"] == "calibrated"
    assert original["value"] == round(
        record["est_request_tokens_original"]["value"] * exact / estimate
    )
    calibrate = span(view, "calibrate")
    assert calibrate["attrs"]["k"] == pytest.approx(exact / estimate)
    assert calibrate["status"] == "ok"

    summary = [json.loads(line) for line in t.log_lines() if '"event": "request"' in line][-1]
    tokens = summary["tokens"]
    assert tokens["saved"] == {"value": round(saved * exact / estimate), "method": "calibrated"}
    assert tokens["usage"]["input"] == exact and tokens["usage"]["method"] == "exact"
    assert tokens["k"] == pytest.approx(exact / estimate)


def test_calibration_outlier_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    upstream.responder = usage_responder({"input_tokens": 10_000_000, "output_tokens": 1})
    view = send(t)
    assert view["record"]["saving"]["method"] == "estimate"
    assert "calibration_outlier" in decisions(view)


def test_health_degraded_on_calibration_outliers(tokli: Start, upstream: FakeUpstream) -> None:
    """OB-011 / A8 / TM-009: more than 20 % outliers over ≥ 20 calibrated requests; one WARNING
    per minute."""
    t = tokli()
    upstream.responder = usage_responder({"input_tokens": 10_000_000, "output_tokens": 1})
    for _ in range(19):
        send(t)
    assert httpx.get(t.url + "/tokli/health").json()["status"] == "ok"
    send(t)
    health = httpx.get(t.url + "/tokli/health").json()
    assert health["status"] == "degraded"
    assert health["checks"]["calibration"] == "outliers: 20 of 20"
    warnings = [line for line in t.log_lines() if '"WARNING"' in line and "calibration" in line]
    assert len(warnings) == 1


def test_estimate_off_latency_path(
    tokli: Start, upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-TM-7 / I1: a slow whole-request estimate never delays the client."""
    from tokli.app import measurement

    real = measurement.estimate_request_tokens

    def slow(*args: Any, **kwargs: Any) -> int:
        time.sleep(2)
        return real(*args, **kwargs)

    monkeypatch.setattr(measurement, "estimate_request_tokens", slow)
    upstream.responder = usage_responder({"input_tokens": 100, "output_tokens": 1})
    t = tokli()
    started = time.monotonic()
    response = httpx.post(
        t.url + "/anthropic/v1/messages", content=request_body(), headers=HEADERS, timeout=10
    )
    elapsed = time.monotonic() - started
    assert response.status_code == 200 and elapsed < 1.5
    record = t.wait_trace(response.headers["x-tokli-request-id"], timeout_s=10)["record"]
    assert record["est_request_tokens_forwarded"]["value"] > 0
    assert record["ms_tokli_overhead"] < 1000


# -- header names, leak scans ------------------------------------------------------------------


def test_header_names_persisted_end_to_end(tokli: Start) -> None:
    t = tokli()
    rid = send(t)["request_id"]
    assert t.services.store is not None
    t.services.store.flush()
    stored = t.services.store.get(rid)
    assert stored is not None
    names = stored["record"]["header_names"]
    assert "x-api-key" in names and names == sorted(names)
    db = (t.services.config.dirs.data_dir / "tokli.db").read_bytes()
    assert b"TOKLI-CANARY-KEY" not in db


def test_response_content_never_recorded(tokli: Start, upstream: FakeUpstream) -> None:
    """Credential and content scans over the usage tee paths (TOKLI_OBSERVABILITY §8)."""
    t = tokli()
    upstream.responder = sse_responder(events("stream_basic.sse"))
    traces = [json.dumps(send(t, request_body(stream=True)))]
    upstream.responder = usage_responder({"input_tokens": 5, "output_tokens": 5})
    traces.append(json.dumps(send(t)))
    assert t.services.store is not None
    t.services.store.flush()
    db = (t.services.config.dirs.data_dir / "tokli.db").read_bytes()
    for sink in (*traces, t.logs.getvalue(), db.decode("latin-1")):
        assert "TOKLI-CANARY" not in sink


def test_stream_metadata_in_summary_log_line(tokli: Start, upstream: FakeUpstream) -> None:
    """E4 needs the SSE event types and `message_delta` usage field names after a restart, so
    the summary log line carries them (metadata only)."""
    upstream.responder = sse_responder(events("stream_basic.sse"))
    t = tokli()
    send(t, request_body(stream=True))
    summary = [json.loads(line) for line in t.log_lines() if '"event": "request"' in line][-1]
    assert summary["sse"]["events"]["message_delta"] == 1
    assert summary["sse"]["delta_usage_fields"] == ["output_tokens"]
