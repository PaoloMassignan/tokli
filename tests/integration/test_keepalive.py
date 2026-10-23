"""SPEC 020 cache keepalive end to end (S8l): AC-KA-1…AC-KA-12, AC-SC-6, AC-TC-19, AC-OB-8.

A real Tokli and a scripted fake upstream; only time is faked. ``FakeTime`` replaces the wall
clock of the conversation store and of the keepalive, and the keepalive's sleep: a sleeping ping
waits until the test lets fake time run up to its due moment, then the clock jumps there.
"""

from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tests.integration.servers import BYTE_CATALOG, FakeUpstream, Tokli, make_config, run_tokli
from tests.unit.test_resume_pruning import body as resume_body
from tokli.app.bootstrap import bootstrap
from tokli.protocols.anthropic_messages import conversation_key, parse

Start = Callable[..., Tokli]
KEY = "sk-ant-api03-TOKLI-CANARY-KEEPALIVE-KEY"
HEADERS = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "anthropic-beta": "beta-x"}
OAUTH = {
    "authorization": "Bearer sk-ant-oat01-TOKLI-CANARY-OAUTH",
    "anthropic-version": "2023-06-01",
}
CANARY = "TOKLI-CANARY-KEEPALIVE-CONTENT"
ON = ("keepalive.enabled=true",)
OFF = ("keepalive.enabled=false",)
CLIENT_MAX = 32000
START = 10_000.0
PREFIX = 60_000  # provider tokens the fake upstream reports as the cached prefix
HOUR = {"type": "ephemeral", "ttl": "1h"}
FIXTURES = Path(__file__).resolve().parents[1] / "compat" / "fixtures" / "anthropic_messages"


class FakeTime:
    def __init__(self, start: float = START) -> None:
        self.now = start
        self.until = start

    def clock(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        target = self.now + max(0.0, delay)
        while target > self.until:
            await asyncio.sleep(0.005)
        self.now = max(self.now, target)

    def jump(self, moment: float) -> None:
        self.now = self.until = moment


def conversation(name: str = "a", **over: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "model": "claude-opus-5-5",
        "max_tokens": CLIENT_MAX,
        "system": [{"type": "text", "text": f"system {CANARY}", "cache_control": HOUR}],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"conversation {name} {CANARY}", "cache_control": HOUR}
                ],
            }
        ],
    }
    data.update(over)
    return data


def is_ping(data: dict[str, Any]) -> bool:
    return data.get("max_tokens") != CLIENT_MAX


def sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


class Script:
    """The fake upstream: client requests report a cached prefix of ``PREFIX`` tokens (or
    ``small`` ones fewer); pings read it and write ``ping_write`` tokens with ``ping_status``."""

    def __init__(self, time_source: FakeTime) -> None:
        self.time = time_source
        self.ping_status: int = 200
        self.ping_write = 0
        self.ping_delay_s = 0.0
        self.client_status: int = 200
        self.client_gate: threading.Event | None = None
        self.ping_times: list[float] = []
        self.ping_bodies: list[dict[str, Any]] = []

    async def __call__(self, request: Request) -> Response:
        data = json.loads(await request.body())
        ping = is_ping(data)
        if ping:
            self.ping_times.append(self.time.now)
            self.ping_bodies.append(data)
            if self.ping_delay_s:
                await asyncio.sleep(self.ping_delay_s)
            if self.ping_status != 200:
                return JSONResponse(
                    {"type": "error", "error": {"type": "x", "message": "no"}},
                    status_code=self.ping_status,
                )
            usage = {
                "input_tokens": 4,
                "cache_read_input_tokens": PREFIX,
                "cache_creation_input_tokens": self.ping_write,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 0,
                    "ephemeral_1h_input_tokens": self.ping_write,
                },
                "output_tokens": 1,
            }
            stop = "max_tokens"
        else:
            gate = self.client_gate
            if gate is not None:
                await asyncio.to_thread(gate.wait, 10)
            if self.client_status != 200:
                return JSONResponse(
                    {"type": "error", "error": {"type": "rate_limit_error", "message": "slow"}},
                    status_code=self.client_status,
                )
            text = json.dumps(data["messages"][0])
            written = 19_999 - 1_000 if "small" in text else PREFIX - 1_000
            usage = {
                "input_tokens": 4,
                "cache_read_input_tokens": 1_000,
                "cache_creation_input_tokens": written,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 0,
                    "ephemeral_1h_input_tokens": written,
                },
                "output_tokens": 50,
            }
            stop = "end_turn"
        if data.get("stream"):
            chunks = [
                sse(
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {"id": "msg_k", "type": "message", "usage": usage},
                    },
                ),
                sse(
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": stop},
                        "usage": {"output_tokens": usage["output_tokens"]},
                    },
                ),
                sse("message_stop", {"type": "message_stop"}),
            ]

            async def gen():  # type: ignore[no-untyped-def]
                for chunk in chunks:
                    yield chunk

            return StreamingResponse(gen(), media_type="text/event-stream")
        return JSONResponse(
            {
                "id": "msg_k",
                "type": "message",
                "role": "assistant",
                "content": [],
                "stop_reason": stop,
                "usage": usage,
            }
        )


def fake_time(t: Tokli) -> FakeTime:
    ft = FakeTime()
    t.services.conversations.clock = ft.clock
    t.services.keepalive.clock = ft.clock
    t.services.keepalive.sleep = ft.sleep
    return ft


def start(tokli: Start, upstream: FakeUpstream, *sets: str) -> tuple[Tokli, FakeTime, Script]:
    t = tokli(*sets)
    ft = fake_time(t)
    script = Script(ft)
    upstream.responder = script
    return t, ft, script


def send(
    t: Tokli, data: dict[str, Any], headers: dict[str, str] | None = None, status: int = 200
) -> dict[str, Any]:
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=json.dumps(data).encode(),
        headers=headers or HEADERS,
        timeout=20,
    )
    assert response.status_code == status, response.text
    if data.get("stream"):
        response.read()
    return t.wait_trace(response.headers["x-tokli-request-id"])


def pings(upstream: FakeUpstream) -> list[dict[str, Any]]:
    return [json.loads(r.body) for r in upstream.received if is_ping(json.loads(r.body))]


def wait_for(condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


def settle(seconds: float = 0.3) -> None:
    """Real time for tasks that must NOT act, to show that they did not."""
    time.sleep(seconds)


def log_events(t: Tokli, event: str) -> list[dict[str, Any]]:
    out = []
    for line in t.log_lines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("event") == event:
            out.append(entry)
    return out


def stops(t: Tokli) -> list[str]:
    return [e["reason"] for e in log_events(t, "keepalive_stop")]


def ping_lines(t: Tokli) -> list[dict[str, Any]]:
    return [e for e in log_events(t, "request") if e.get("outcome") == "keepalive"]


def ping_record(t: Tokli, index: int = -1) -> dict[str, Any]:
    wait_for(lambda: len(ping_lines(t)) >= (index + 1 if index >= 0 else 1))
    rid = ping_lines(t)[index]["request_id"]
    return t.wait_trace(rid)


# -- AC-KA-1, AC-SC-6 -----------------------------------------------------------------------


def test_keepalive_off_sends_nothing(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-1 (KA-001): with `keepalive.enabled` false, a cached one-hour request and two hours
    of fake time give no request beyond the client's."""
    t, ft, _ = start(tokli, upstream, *OFF)
    send(t, conversation())
    ft.until = START + 7200
    settle()
    assert len(upstream.received) == 1
    assert len(t.services.keepalive) == 0


def test_keepalive_on_by_default(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-1 (KA-001 after S8l SCR-004): with the default configuration, an eligible request
    with an OAuth credential is kept and pinged."""
    t, ft, script = start(tokli, upstream)
    trace = send(t, conversation(), OAUTH)
    assert trace["trace"]["attrs"]["keepalive"] == "kept"
    ft.until = START + 3600
    wait_for(lambda: len(pings(upstream)) == 1)
    assert script.ping_times == [START + 3300]


def _post_fixtures(t: Tokli) -> list[dict[str, Any]]:
    sent = []
    for path in sorted(FIXTURES.glob("*.json")):
        response = httpx.post(
            t.url + "/anthropic/v1/messages",
            content=path.read_bytes(),
            headers=HEADERS,
            timeout=20,
        )
        assert response.status_code == 200
        response.read()
        sent.append(json.loads(path.read_bytes()))
    return sent


def test_no_originated_requests_when_off(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-SC-6 (SC-008): with `keepalive.enabled` false, over every compat fixture and two hours
    of fake time, the upstream receives only what clients sent."""
    t, ft, _ = start(tokli, upstream, *OFF)
    sent = _post_fixtures(t)
    send(t, conversation())
    ft.until = START + 7200
    settle()
    assert len(upstream.received) == len(sent) + 1


def test_originated_requests_are_keepalives_only(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-SC-6 (SC-008 after S8l SCR-004): with the default configuration, every request Tokli
    originates is a keepalive: a body a client sent, with only `max_tokens` changed."""
    t, ft, _ = start(tokli, upstream)
    _post_fixtures(t)
    send(t, conversation())
    clients = [json.loads(r.body) for r in upstream.received]
    ft.until = START + 7200
    wait_for(lambda: len(upstream.received) > len(clients))
    settle()
    originated = [json.loads(r.body) for r in upstream.received[len(clients) :]]
    assert originated
    for ping in originated:
        assert ping["max_tokens"] == 1
        assert any({**ping, "max_tokens": c["max_tokens"]} == c for c in clients), (
            "an originated request is not a client body with max_tokens changed"
        )


# -- AC-KA-2 ---------------------------------------------------------------------------------


def test_keepalive_eligibility_reasons(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-2 (KA-002, KA-010) and AC-OB-8's client side: a 5 min marker, a prefix of 19,999
    tokens, an OAuth credential without `keepalive.oauth`, and a 429 are each not kept, with the
    reason in the trace; a one-hour request with a large prefix is kept."""
    t, _, script = start(tokli, upstream, *ON, "keepalive.oauth=false")
    five = conversation("five")
    five["system"][0]["cache_control"] = {"type": "ephemeral"}
    five["messages"][0]["content"][0]["cache_control"] = {"type": "ephemeral"}
    cases = [
        (five, HEADERS, 200, "ineligible(short_ttl)"),
        (conversation("small"), HEADERS, 200, "ineligible(too_small)"),
        (conversation("oauth"), OAUTH, 200, "ineligible(oauth_not_enabled)"),
    ]
    for data, headers, status, reason in cases:
        trace = send(t, data, headers, status)
        assert trace["trace"]["attrs"]["keepalive"] == reason
        assert {"decision": "keepalive", "reason": reason} in trace["trace"]["decisions"]
    script.client_status = 429
    trace = send(t, conversation("busy"), status=429)
    assert trace["trace"]["attrs"]["keepalive"] == "ineligible(upstream_status)"
    script.client_status = 200
    assert len(t.services.keepalive) == 0
    trace = send(t, conversation("kept"))
    assert trace["trace"]["attrs"]["keepalive"] == "kept"
    assert trace["trace"]["attrs"]["keepalive_bridged"] is False
    assert len(t.services.keepalive) == 1


def test_keepalive_oauth_opt_in(tokli: Start, upstream: FakeUpstream) -> None:
    """KA-002: with `keepalive.oauth` on, an OAuth conversation is kept."""
    t, _, _ = start(tokli, upstream, *ON, "keepalive.oauth=true")
    trace = send(t, conversation("oauth"), OAUTH)
    assert trace["trace"]["attrs"]["keepalive"] == "kept"


# -- AC-KA-3 ---------------------------------------------------------------------------------


def _without(headers: list[tuple[str, str]], *names: str) -> list[tuple[str, str]]:
    return [(k.lower(), v) for k, v in headers if k.lower() not in names]


def test_ping_body_changes_only_max_tokens(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-3 (KA-004): a streamed request with adaptive thinking and two markers; the ping's
    JSON equals the forwarded JSON except `max_tokens: 1`, and its headers equal the forwarded
    headers."""
    t, ft, _ = start(tokli, upstream, *ON)
    data = conversation(stream=True, thinking={"type": "adaptive"})
    send(t, data)
    forwarded = upstream.received[-1]
    ft.until = START + 3300
    wait_for(lambda: len(pings(upstream)) == 1)
    ping = upstream.received[-1]
    expected = json.loads(forwarded.body)
    expected["max_tokens"] = 1
    assert json.loads(ping.body) == expected
    assert _without(ping.headers, "content-length") == _without(forwarded.headers, "content-length")


def test_ping_max_tokens_above_thinking_budget(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-3 (KA-004): with `thinking: {type: enabled, budget_tokens: 2048}` the ping has
    `max_tokens: 2049`."""
    t, ft, _ = start(tokli, upstream, *ON)
    send(t, conversation(thinking={"type": "enabled", "budget_tokens": 2048}))
    ft.until = START + 3300
    wait_for(lambda: len(pings(upstream)) == 1)
    assert pings(upstream)[0]["max_tokens"] == 2049


# -- AC-KA-4, AC-KA-5 ------------------------------------------------------------------------


def test_ping_schedule_until_horizon(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-4 (KA-005): one-hour lifetime, `lead_s` 300, 12 h horizon: pings every 55 min,
    none later than 12 h after the client request: 13 pings; the last one stops the
    conversation with `horizon`."""
    t, ft, script = start(tokli, upstream, *ON)
    send(t, conversation())
    ft.until = START + 13 * 3600
    wait_for(lambda: "horizon" in stops(t), timeout_s=15)
    assert script.ping_times == [START + 3300 * k for k in range(1, 14)]
    assert ping_record(t, 12)["record"]["keepalive_stop_reason"] == "horizon"
    assert len(t.services.keepalive) == 0


def test_ping_not_sent_after_clock_jump(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-5 (KA-006): a clock that jumps 2 h before a due ping gives no ping and `expired`."""
    t, ft, _ = start(tokli, upstream, *ON)
    send(t, conversation())
    ft.jump(START + 7200)
    wait_for(lambda: "expired" in stops(t))
    assert pings(upstream) == []
    assert len(t.services.keepalive) == 0


# -- AC-KA-6, AC-TC-19 -----------------------------------------------------------------------


def test_ping_cache_missed_stops(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-6 (KA-007): a ping answered with a cache write of 60 % of the prefix stops the
    conversation with `cache_missed`."""
    t, ft, script = start(tokli, upstream, *ON)
    send(t, conversation())
    script.ping_write = int(PREFIX * 0.6)
    ft.until = START + 3 * 3600
    wait_for(lambda: "cache_missed" in stops(t))
    settle()
    assert len(pings(upstream)) == 1
    assert ping_record(t)["record"]["keepalive_stop_reason"] == "cache_missed"


def test_ping_auth_rejected_stops(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-6 (KA-008) and AC-TC-19: a ping answered 401 stops with `auth_rejected`, is not
    retried, and persists a `keepalive` row with the reason."""
    t, ft, script = start(tokli, upstream, *ON)
    send(t, conversation())
    script.ping_status = 401
    ft.until = START + 3 * 3600
    wait_for(lambda: "auth_rejected" in stops(t))
    settle()
    assert len(pings(upstream)) == 1
    record = ping_record(t)["record"]
    assert record["outcome"] == "keepalive"
    assert record["status_code"] == 401
    assert record["keepalive_stop_reason"] == "auth_rejected"


def test_ping_upstream_error_stops_without_retry(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-6 (KA-008): a ping answered 529 stops with `upstream_error`; none is retried."""
    t, ft, script = start(tokli, upstream, *ON)
    send(t, conversation())
    script.ping_status = 529
    ft.until = START + 3 * 3600
    wait_for(lambda: "upstream_error" in stops(t))
    settle()
    assert len(pings(upstream)) == 1


def test_ping_timeout_stops_without_retry(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-6 (KA-008, KA-014): a ping that times out (the upstream's read timeout) stops with
    `upstream_error`."""
    t, ft, script = start(tokli, upstream, *ON, "upstreams.anthropic.read_timeout_s=0.5")
    send(t, conversation())
    script.ping_delay_s = 3.0
    ft.until = START + 3 * 3600
    wait_for(lambda: "upstream_error" in stops(t), timeout_s=10)
    assert len(pings(upstream)) == 1


def test_keepalive_rows_persisted(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-TC-19 (TC-023): a successful ping persists a `keepalive` row with usage, status and a
    null stop reason, null estimate fields, and no compressor rows; the client request's row
    carries `keepalive_bridged` false and its cache lifetime."""
    t, ft, _ = start(tokli, upstream, *ON)
    client = send(t, conversation())
    ft.until = START + 3300
    wait_for(lambda: len(ping_lines(t)) == 1)
    assert t.services.store is not None
    t.services.store.flush()
    stored = t.services.store.get(ping_lines(t)[0]["request_id"])
    assert stored is not None
    record = stored["record"]
    assert record["outcome"] == "keepalive"
    assert (record["status_code"], record["usage_cache_read"], record["usage_output"]) == (
        200,
        PREFIX,
        1,
    )
    assert record["keepalive_stop_reason"] is None
    assert record["stop_reason"] == "max_tokens"
    assert record["est_original_tokens"] is None and record["est_request_tokens_forwarded"] is None
    assert record["credential_kind"] == "api_key"
    assert stored["compressors"] == []
    client_row = t.services.store.get(client["request_id"])
    assert client_row is not None
    assert client_row["record"]["keepalive_bridged"] is False
    assert client_row["record"]["cache_ttl_s"] == 3600


# -- AC-KA-7, AC-KA-8 ------------------------------------------------------------------------


def test_keepalive_evicts_oldest(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-7 (KA-009): with `max_conversations` 2, a third kept conversation evicts the one
    whose last client request is oldest."""
    t, ft, _ = start(tokli, upstream, *ON, "keepalive.max_conversations=2")
    for name, moment in (("one", START), ("two", START + 10), ("three", START + 20)):
        ft.jump(moment)
        send(t, conversation(name))
    assert stops(t) == ["evicted"]
    assert len(t.services.keepalive) == 2
    ft.until = START + 3400
    wait_for(lambda: len(pings(upstream)) == 2)
    pinged = {json.dumps(p["messages"][0]) for p in pings(upstream)}
    assert not any("conversation one" in text for text in pinged)


def _patch(t: Tokli, changes: dict[str, Any]) -> None:
    response = httpx.patch(t.url + "/tokli/api/config", json={"changes": changes}, timeout=10)
    assert response.status_code == 200, response.text


def test_keepalive_disabled_at_run_time(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-8 (KA-011, CF-009 after S8l SCR-001): the feature is turned on and off through the
    config API; turning it off stops every kept conversation with `disabled`; no ping
    follows."""
    t, ft, _ = start(tokli, upstream)
    _patch(t, {"keepalive.enabled": True})
    send(t, conversation("one"))
    send(t, conversation("two"))
    assert len(t.services.keepalive) == 2
    _patch(t, {"keepalive.enabled": False})
    wait_for(lambda: stops(t).count("disabled") == 2)
    ft.until = START + 3 * 3600
    settle()
    assert pings(upstream) == []
    assert len(t.services.keepalive) == 0


def test_keepalive_shutdown_drops_state(tmp_path: Path, upstream: FakeUpstream) -> None:
    """AC-KA-8 (KA-011): stopping the server stops every kept conversation with `shutdown`."""
    config = make_config(tmp_path, upstream.url, *ON)
    services = bootstrap(config, catalog=BYTE_CATALOG, version="test")
    with run_tokli(config, services) as t:
        ft = fake_time(t)
        upstream.responder = Script(ft)
        send(t, conversation())
        assert len(t.services.keepalive) == 1
    assert "shutdown" in stops(t)
    assert len(services.keepalive) == 0
    assert pings(upstream) == []


# -- AC-KA-9, AC-KA-10 -----------------------------------------------------------------------


def test_no_ping_while_client_request_in_flight(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-9 (KA-012): a ping due while a client request of the same conversation is in
    flight is not sent; the scheduling restarts from that request."""
    t, ft, script = start(tokli, upstream, *ON)
    send(t, conversation())
    ft.jump(START + 1000)
    gate = threading.Event()
    script.client_gate = gate
    result: list[dict[str, Any]] = []
    second = threading.Thread(target=lambda: result.append(send(t, conversation())))
    second.start()
    wait_for(lambda: len(upstream.received) == 2)
    ft.until = START + 4000  # past the first request's due ping (START + 3300)
    settle()
    assert pings(upstream) == []
    script.client_gate = None
    gate.set()
    second.join(timeout=10)
    assert result
    settle()
    assert pings(upstream) == []  # the next ping is due at START + 1000 + 3300
    ft.until = START + 4300
    wait_for(lambda: len(pings(upstream)) == 1)
    assert script.ping_times == [START + 4300]


def _with_marker(data: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(data)
    last = data["messages"][-1]
    if isinstance(last["content"], str):
        last["content"] = [{"type": "text", "text": last["content"]}]
    last["content"][-1]["cache_control"] = HOUR
    data["max_tokens"] = CLIENT_MAX
    return data


def test_successful_ping_prevents_resume(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-10 (KA-013, PR-021 and PR-024 after S8l SCR-001) and TC-024: with
    `edit_args_on_resume` on, a client request 1 h 50 min after the previous one, with a
    successful ping at 55 min, is not a resume; its forwarded pruned calls are byte-identical,
    and its record says it was bridged."""
    t, ft, _ = start(tokli, upstream, *ON, "compressors.edit_args_on_resume.enabled=true")
    data = _with_marker(resume_body(turns_after_write=6, turns_after_edit=2))
    send(t, data)
    sent_first = json.loads(upstream.received[-1].body)
    ft.until = START + 3300
    wait_for(lambda: len(pings(upstream)) == 1)
    ft.jump(START + 6600 - 100)
    trace = send(t, data)
    span = next(s for s in trace["trace"]["spans"] if s["name"] == "conversation")
    assert span["attrs"]["resume"] is False
    sent_second = json.loads(upstream.received[-1].body)
    assert sent_second["messages"][:-1] == sent_first["messages"][:-1]
    assert trace["record"]["keepalive_bridged"] is True
    assert trace["trace"]["attrs"]["keepalive_bridged"] is True


def test_without_ping_the_same_request_is_a_resume(tokli: Start, upstream: FakeUpstream) -> None:
    """The control of AC-KA-10: with the keepalive off, the same timeline is a resume."""
    t, ft, _ = start(tokli, upstream, *OFF, "compressors.edit_args_on_resume.enabled=true")
    data = _with_marker(resume_body(turns_after_write=6, turns_after_edit=2))
    send(t, data)
    ft.jump(START + 6600 - 100)
    trace = send(t, data)
    span = next(s for s in trace["trace"]["spans"] if s["name"] == "conversation")
    assert span["attrs"]["resume"] is True
    assert trace["record"]["keepalive_bridged"] is None


# -- AC-KA-11, AC-KA-12, AC-OB-8 -------------------------------------------------------------


def _files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_keepalive_never_persists_content_or_credentials(
    tokli: Start, upstream: FakeUpstream, tmp_path: Path
) -> None:
    """AC-KA-11 (KA-003, KA-015, UP-002 after S8l SCR-001): canary credentials and content of a
    kept conversation never appear in logs, the database, traces or API responses; nothing is
    written in the data directory beyond the telemetry files."""
    t, ft, script = start(tokli, upstream, *ON)
    data_dir = tmp_path / "data"
    before = _files(data_dir)
    first = send(t, conversation())
    ft.until = START + 3300
    wait_for(lambda: len(ping_lines(t)) == 1)
    script.ping_status = 401
    ft.until = START + 3 * 3600
    wait_for(lambda: "auth_rejected" in stops(t))
    assert t.services.store is not None
    t.services.store.flush()
    outputs = [t.logs.getvalue()]
    for line in ping_lines(t):
        outputs.append(json.dumps(t.wait_trace(line["request_id"])))
    outputs.append(json.dumps(t.wait_trace(first["request_id"])))
    for path in ("/tokli/api/requests", "/tokli/api/metrics/summary"):
        outputs.append(httpx.get(t.url + path, timeout=10).text)
    for path in data_dir.rglob("*"):
        if path.is_file():
            outputs.append(path.read_bytes().decode("latin-1"))
    blob = "\n".join(outputs)
    assert KEY not in blob and "TOKLI-CANARY-KEEPALIVE-KEY" not in blob
    assert CANARY not in blob
    added = _files(data_dir) - before
    assert added <= {"tokli.db", "tokli.db-wal", "tokli.db-shm"}, added


def test_ping_does_not_delay_client_requests(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-KA-12 (KA-014): a ping whose upstream answers after 5 s does not delay a concurrent
    client request."""
    t, ft, script = start(tokli, upstream, *ON)
    send(t, conversation("one"))
    script.ping_delay_s = 5.0
    ft.until = START + 3300
    wait_for(lambda: len(script.ping_times) == 1)
    began = time.monotonic()
    send(t, conversation("two"))
    assert time.monotonic() - began < 2.0


def test_keepalive_trace_and_log_line(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-OB-8 (OB-014): a ping has a trace with the spans `keepalive`, `upstream` and `usage`,
    a log line and a DB row sharing one request id, with no conversation key, header value or
    content in any of them."""
    t, ft, _ = start(tokli, upstream, *ON)
    data = conversation()
    send(t, data)
    ft.until = START + 3300
    wait_for(lambda: len(ping_lines(t)) == 1)
    line = ping_lines(t)[0]
    view = t.wait_trace(line["request_id"])
    names = [s["name"] for s in view["trace"]["spans"]]
    assert {"keepalive", "upstream", "usage"} <= set(names)
    span = next(s for s in view["trace"]["spans"] if s["name"] == "keepalive")
    assert span["attrs"]["prefix_tokens"] == PREFIX
    assert span["attrs"]["cache_ttl_s"] == 3600
    assert span["attrs"]["since_client_s"] == 3300
    assert view["record"]["request_id"] == line["request_id"]
    assert line["status"] == 200
    key = conversation_key(parse(json.dumps(data).encode(), mutable_kinds=frozenset()))
    blob = json.dumps(view) + json.dumps(line)
    for secret in (key, KEY, CANARY, "beta-x"):
        assert secret not in blob
