"""SPEC 002 / 003 / 006 end to end: routing, relay, streaming, errors, headers, credentials."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tests.integration.servers import FakeUpstream, Tokli, free_socket

FIXTURES = Path(__file__).resolve().parents[1] / "compat" / "fixtures" / "anthropic_messages"
ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
CLIENT_HEADERS = {
    "x-api-key": "sk-ant-api03-TOKLI-CANARY-KEY",
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "prompt-caching-2024-07-31",
    "content-type": "application/json",
}

Start = Callable[..., Tokli]


def body(name: str) -> bytes:
    return (FIXTURES / f"{name}.json").read_bytes()


def post(
    tokli: Tokli, path: str = "/anthropic/v1/messages", content: bytes | None = None, **kw: object
) -> httpx.Response:
    headers = {**CLIENT_HEADERS, **kw.pop("headers", {})}  # type: ignore[dict-item]
    return httpx.post(
        tokli.url + path,
        content=content if content is not None else body("string_content"),
        headers=headers,
        timeout=10,
        **kw,
    )  # type: ignore[arg-type]


def test_routing_table(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    assert post(t, "/anthropic/v1/messages/").status_code == 200
    assert upstream.received[-1].path == "/v1/messages"
    assert (
        post(t, "/anthropic/messages").status_code == 200
    )  # a missing /v1 is added for known endpoints
    assert upstream.received[-1].path == "/v1/messages"
    httpx.get(t.url + "/anthropic/v1/models?limit=5", headers=CLIENT_HEADERS)
    assert (
        upstream.received[-1].method,
        upstream.received[-1].path,
        upstream.received[-1].query,
    ) == (
        "GET",
        "/v1/models",
        "limit=5",
    )


@pytest.mark.parametrize("path", ["/openai/v1/chat/completions", "/unknown/x", "/", "/v1/messages"])
def test_unknown_prefix_returns_tokli_404(tokli: Start, upstream: FakeUpstream, path: str) -> None:
    response = post(tokli(), path)
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["type"] == "tokli_unknown_route" and error["source"] == "tokli"
    assert "/anthropic" in error["message"]
    assert upstream.received == []


def test_headers_forwarded_except_hop_by_hop(tokli: Start, upstream: FakeUpstream) -> None:
    post(
        tokli(),
        headers={
            "x-custom": "1",
            "keep-alive": "timeout=5",
            "te": "trailers",
            "proxy-authorization": "Basic Zm9v",
            "connection": "keep-alive, x-drop",
            "x-drop": "y",
            "user-agent": "claude-cli/9.9.9 (test)",
        },
    )
    seen = {k.lower(): v for k, v in upstream.received[-1].headers}
    assert seen["x-custom"] == "1"
    for name in ("keep-alive", "te", "proxy-authorization", "x-drop"):
        assert name not in seen
    assert seen["host"].startswith("127.0.0.1:")
    assert seen["user-agent"] == "claude-cli/9.9.9 (test)"  # exactly the client's; Tokli adds none
    names = [k.lower() for k, _ in upstream.received[-1].headers]
    assert names.count("user-agent") == 1


def test_passthrough_forwards_client_credentials(tokli: Start, upstream: FakeUpstream) -> None:
    post(tokli(), headers={"authorization": "Bearer sk-ant-oat01-TOKLI-CANARY-OAUTH"})
    seen = {k.lower(): v for k, v in upstream.received[-1].headers}
    assert seen["x-api-key"] == CLIENT_HEADERS["x-api-key"]
    assert seen["authorization"] == "Bearer sk-ant-oat01-TOKLI-CANARY-OAUTH"
    assert seen["anthropic-beta"] == CLIENT_HEADERS["anthropic-beta"]
    assert seen["anthropic-version"] == CLIENT_HEADERS["anthropic-version"]


def test_body_independent_of_auth_mode(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    post(t, content=body("tool_use_and_results"))
    post(
        t,
        content=body("tool_use_and_results"),
        headers={"x-api-key": "other", "authorization": "Bearer x"},
    )
    assert upstream.received[0].body == upstream.received[1].body


def test_inherited_provider_env_is_ignored_unless_configured(
    tokli: Start, upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-TOKLI-CANARY-INHERITED")
    t = tokli()
    httpx.post(
        t.url + "/anthropic/v1/messages",
        content=body("string_content"),
        headers={"content-type": "application/json"},
        timeout=10,
    )
    names = {k.lower() for k, _ in upstream.received[-1].headers}
    assert "x-api-key" not in names and "authorization" not in names


def test_response_bytes_identical(tokli: Start, upstream: FakeUpstream) -> None:
    payload = b'{"id":"msg_1","content":[{"type":"text","text":"caf\xc3\xa9"}],"x":  1}'

    async def responder(request: Request) -> Response:
        return Response(
            payload,
            status_code=201,
            media_type="application/json",
            headers={"x-upstream": "yes", "request-id": "req_TEST123"},
        )

    upstream.responder = responder
    response = post(tokli())
    assert response.status_code == 201
    assert response.content == payload
    assert response.headers["x-upstream"] == "yes"
    assert response.headers["content-type"] == "application/json"
    assert ULID.match(response.headers["x-tokli-request-id"])


def test_request_id_header_can_be_disabled(tokli: Start) -> None:
    assert "x-tokli-request-id" not in post(tokli("observability.response_header=false")).headers


def test_request_id_header(tokli: Start) -> None:
    first, second = post(tokli()), None
    assert ULID.match(first.headers["x-tokli-request-id"])
    second = post(tokli())
    assert first.headers["x-tokli-request-id"] != second.headers["x-tokli-request-id"]


@pytest.mark.parametrize("status", [400, 401, 429, 529])
@pytest.mark.parametrize("stream", [False, True])
def test_upstream_errors_relayed_verbatim(
    tokli: Start, upstream: FakeUpstream, status: int, stream: bool
) -> None:
    error = json.dumps(
        {"type": "error", "error": {"type": "some_error", "message": f"status {status}"}}
    ).encode()

    async def responder(request: Request) -> Response:
        return Response(
            error, status_code=status, media_type="application/json", headers={"x-err": "1"}
        )

    upstream.responder = responder
    content = json.dumps({**json.loads(body("string_content")), "stream": stream}).encode()
    response = post(tokli(), content=content)
    assert response.status_code == status
    assert response.content == error
    assert response.headers["x-err"] == "1"


def test_upstream_unreachable_returns_tokli_502(tokli: Start) -> None:
    sock = free_socket()
    port = sock.getsockname()[1]
    sock.close()  # nothing listens there any more
    response = post(tokli(base_url=f"http://127.0.0.1:{port}"))
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["type"] == "tokli_upstream_unreachable" and error["source"] == "tokli"
    assert error["request_id"] == response.headers["x-tokli-request-id"]


def test_upstream_timeout_returns_tokli_504(tokli: Start, upstream: FakeUpstream) -> None:
    async def slow(request: Request) -> Response:
        await asyncio.sleep(3)
        return JSONResponse({})

    upstream.responder = slow
    response = post(tokli("upstreams.anthropic.read_timeout_s=0.5"))
    assert response.status_code == 504
    assert response.json()["error"]["type"] == "tokli_upstream_timeout"


def sse(event: str, data: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def test_stream_chunks_identical_and_unbuffered(tokli: Start, upstream: FakeUpstream) -> None:
    """Causal relay test (AC-PX-3): chunk n+1 is sent only after the client received chunk n."""
    chunks = [sse("content_block_delta", {"i": i, "text": "x" * i}) for i in range(10)]
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
    content = json.dumps({**json.loads(body("string_content")), "stream": True}).encode()
    got = b""
    with httpx.stream(
        "POST",
        tokli().url + "/anthropic/v1/messages",
        content=content,
        headers=CLIENT_HEADERS,
        timeout=15,
    ) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        for piece in response.iter_raw():
            got += piece
            for i in range(len(chunks)):
                if got.startswith(b"".join(chunks[: i + 1])):
                    received[i].set()
    assert stalled == []
    assert got == b"".join(chunks)


def test_client_disconnect_cancels_upstream(tokli: Start, upstream: FakeUpstream) -> None:
    cancelled = threading.Event()

    async def responder(request: Request) -> Response:
        async def gen() -> AsyncIterator[bytes]:
            try:
                for i in range(200):
                    yield sse("ping", {"i": i})
                    await asyncio.sleep(0.05)
            finally:
                cancelled.set()

        return StreamingResponse(gen(), media_type="text/event-stream")

    upstream.responder = responder
    content = json.dumps({**json.loads(body("string_content")), "stream": True}).encode()
    t = tokli()
    with httpx.stream(
        "POST",
        t.url + "/anthropic/v1/messages",
        content=content,
        headers=CLIENT_HEADERS,
        timeout=10,
    ) as response:
        next(response.iter_raw())
    start = time.monotonic()
    assert cancelled.wait(5), "upstream stream was not cancelled"
    assert time.monotonic() - start < 2  # PX-009 asks for 1 s; slack for CI scheduling


def test_read_timeout_between_chunks(tokli: Start, upstream: FakeUpstream) -> None:
    async def responder(request: Request) -> Response:
        async def gen() -> AsyncIterator[bytes]:
            yield sse("message_start", {"ok": True})
            await asyncio.sleep(3)
            yield sse("never", {})

        return StreamingResponse(gen(), media_type="text/event-stream")

    upstream.responder = responder
    content = json.dumps({**json.loads(body("string_content")), "stream": True}).encode()
    start = time.monotonic()
    got = b""
    with httpx.stream(
        "POST",
        tokli("upstreams.anthropic.read_timeout_s=0.5").url + "/anthropic/v1/messages",
        content=content,
        headers=CLIENT_HEADERS,
        timeout=10,
    ) as response:
        try:
            for piece in response.iter_raw():
                got += piece
        except httpx.HTTPError:
            pass  # the relay ends the stream after the upstream read timeout
    assert got.startswith(sse("message_start", {"ok": True}))
    assert b"never" not in got
    assert time.monotonic() - start < 2.5


def test_anthropic_other_endpoints_verbatim(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    post(t, "/anthropic/v1/messages/count_tokens", content=body("tool_use_and_results"))
    assert upstream.received[-1].body == body("tool_use_and_results")
    assert upstream.received[-1].path == "/v1/messages/count_tokens"


def test_large_body_not_rejected(tokli: Start, upstream: FakeUpstream) -> None:
    content = body("tool_use_and_results")
    response = post(tokli("limits.max_transform_bytes=1000"), content=content)
    assert response.status_code == 200
    assert upstream.received[-1].body == content  # relayed verbatim (too_large)


def test_malformed_body_relayed_verbatim(tokli: Start, upstream: FakeUpstream) -> None:
    for content in (b"{not json", b"[1,2]", b'{"messages": "x"}'):
        assert post(tokli(), content=content).status_code == 200
        assert upstream.received[-1].body == content


def test_content_encoded_body_relayed_verbatim(tokli: Start, upstream: FakeUpstream) -> None:
    import gzip

    content = gzip.compress(body("tool_use_and_results"))
    post(tokli(), content=content, headers={"content-encoding": "gzip"})
    assert upstream.received[-1].body == content


def test_internal_error_forwards_original(
    tokli: Start, upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tokli.http import proxy

    def broken(*args: object, **kwargs: object) -> bytes:
        raise RuntimeError("render bug")

    monkeypatch.setattr(proxy, "render", broken)
    content = body("tool_use_and_results")
    assert post(tokli(), content=content).status_code == 200
    assert upstream.received[-1].body == content


def test_health_endpoint(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    health = httpx.get(t.url + "/tokli/health").json()
    assert health["status"] == "ok"
    assert health["version"] == "test"
    assert health["checks"] == {"telemetry": "ok", "compressors": "ok", "calibration": "ok"}
    assert upstream.received == []


def test_oversize_body_relayed_verbatim(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli("limits.max_transform_bytes=1000")
    content = body("tool_use_and_results")
    response = post(t, content=content)
    assert upstream.received[-1].body == content
    trace = t.wait_trace(response.headers["x-tokli-request-id"])
    assert trace["record"]["passthrough_reason"] == "too_large"
