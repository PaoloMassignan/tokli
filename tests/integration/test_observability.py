"""SPEC 013 / 014 / 015 end to end: traces, reason codes, logs, telemetry rows, API, leak scans."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

from tests.integration.servers import FakeUpstream, Tokli
from tokli.observability import reasons

FIXTURES = Path(__file__).resolve().parents[1] / "compat" / "fixtures" / "anthropic_messages"
ALL = sorted(p.stem for p in FIXTURES.glob("*.json"))
KEY = "sk-ant-api03-TOKLI-CANARY-KEY-SECRET"
HEADERS = {"x-api-key": KEY, "anthropic-version": "2023-06-01"}
Start = Callable[..., Tokli]


def send(
    tokli: Tokli, name: str = "tool_use_and_results", *, stream: bool | None = None
) -> httpx.Response:
    content = (FIXTURES / f"{name}.json").read_bytes()
    if stream is not None:
        content = json.dumps({**json.loads(content), "stream": stream}).encode()
    response = httpx.post(
        tokli.url + "/anthropic/v1/messages", content=content, headers=HEADERS, timeout=10
    )
    tokli.wait_trace(response.headers["x-tokli-request-id"])
    return response


def trace_of(tokli: Tokli, response: httpx.Response) -> dict[str, Any]:
    return tokli.wait_trace(response.headers["x-tokli-request-id"])


def db_rows(tokli: Tokli, table: str) -> list[dict[str, Any]]:
    assert tokli.services.store is not None
    tokli.services.store.flush()
    path = tokli.services.config.dirs.data_dir / "tokli.db"
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute(f"SELECT * FROM {table}")]


def test_trace_contains_all_spans(tokli: Start) -> None:
    t = tokli()
    response = send(t, stream=True)
    trace = trace_of(t, response)
    names = [s["name"] for s in trace["trace"]["spans"]]
    for expected in (
        "route",
        "parse",
        "analyze.reminders",
        "analyze.features",
        "transform.compression",
        "render",
        "auth",
        "upstream",
        "usage",
    ):
        assert expected in names, expected
    assert all(s["ms"] >= 0 for s in trace["trace"]["spans"])
    record = trace["record"]
    assert record["ms_tokli_overhead"] >= 0
    assert record["ms_tokli_overhead"] <= record["ms_total"] - record["ms_upstream_total"] + 1e-6


def test_trace_shows_routing_counts(tokli: Start) -> None:
    t = tokli()
    trace = trace_of(t, send(t))
    stats = {c["compressor_id"]: c for c in trace["compressors"]}
    json_minify = stats["json_minify"]
    assert json_minify["considered"] >= 1 and json_minify["accepted"] >= 1
    assert json_minify["skip_reasons"].get("verbatim_tool", 0) >= 1
    assert trace["record"]["outcome"] == "compressed"


def test_trace_records_header_names_only(tokli: Start) -> None:
    t = tokli()
    trace = trace_of(t, send(t))
    names = trace["trace"]["attrs"]["header_names"]
    assert "x-api-key" in names and "anthropic-version" in names
    assert names == sorted(names)
    assert KEY not in json.dumps(trace)


def test_request_id_propagates_everywhere(tokli: Start) -> None:
    t = tokli()
    response = send(t)
    rid = response.headers["x-tokli-request-id"]
    assert trace_of(t, response)["request_id"] == rid
    summaries = [json.loads(line) for line in t.log_lines() if '"request"' in line]
    assert [s["request_id"] for s in summaries if s.get("event") == "request"] == [rid]
    assert [r["request_id"] for r in db_rows(t, "requests")] == [rid]
    assert {r["request_id"] for r in db_rows(t, "compressor_stats")} == {rid}


def test_request_summary_log_line(tokli: Start) -> None:
    t = tokli()
    send(t)
    lines = [json.loads(line) for line in t.log_lines()]
    summaries = [line for line in lines if line.get("event") == "request"]
    assert len(summaries) == 1
    summary = summaries[0]
    for field in ("request_id", "provider", "model", "outcome", "reason", "status", "overhead_ms"):
        assert field in summary, field
    assert summary["tokens"]["original"]["method"] == "estimate"
    assert summary["level"] == "INFO"


def test_request_record_persisted_per_outcome(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    send(t, "tool_use_and_results")  # compressed
    send(t, "string_content")  # passthrough

    async def too_many(request: Request) -> Response:
        return Response(
            b'{"type":"error","error":{"type":"rate_limit_error","message":"slow"}}',
            status_code=429,
        )

    upstream.responder = too_many
    send(t, "string_content")
    rows = db_rows(t, "requests")
    assert [(r["outcome"], r["status_code"]) for r in rows] == [
        ("compressed", 200),
        ("passthrough", 200),
        ("passthrough", 429),
    ]
    assert rows[1]["passthrough_reason"] in {"no_applicable_compressor", "no_gain"}
    assert rows[0]["credential_kind"] == "api_key"
    assert rows[0]["history_rewritten"] == 0 and rows[0]["reference_stubs"] == 0


def test_compressor_stats_only_for_considered(tokli: Start) -> None:
    t = tokli("compressors.json_minify.enabled=false")
    send(t)
    assert db_rows(t, "compressor_stats") == []
    t2 = tokli()
    send(t2)
    assert [r["compressor_id"] for r in db_rows(t2, "compressor_stats")] == ["json_minify"]


def test_reason_codes_closed_set(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    responses = [send(t, name) for name in ALL]
    responses.append(httpx.post(t.url + "/anthropic/v1/messages", content=b"{bad", headers=HEADERS))
    responses.append(httpx.get(t.url + "/anthropic/v1/models", headers=HEADERS))
    codes: set[str] = set()
    for response in responses:
        trace = trace_of(t, response)
        codes.update(d["reason"] for d in trace["trace"]["decisions"])
        for compressor in trace["compressors"]:
            codes.update(compressor["skip_reasons"])
    assert codes
    unknown = {c for c in codes if not reasons.is_known(c)}
    assert unknown == set()


def test_upstream_correlation_ids_recorded(tokli: Start, upstream: FakeUpstream) -> None:
    async def responder(request: Request) -> Response:
        return Response(
            b"{}", media_type="application/json", headers={"request-id": "req_TOKLI123"}
        )

    upstream.responder = responder
    t = tokli()
    assert trace_of(t, send(t))["trace"]["attrs"]["upstream_request_id"] == "req_TOKLI123"


def test_upstream_error_logging_respects_content_rule(tokli: Start, upstream: FakeUpstream) -> None:
    async def responder(request: Request) -> Response:
        return Response(
            json.dumps(
                {
                    "type": "error",
                    "error": {"type": "invalid_request_error", "message": "bad field"},
                    "echo": "TOKLI-CANARY-ERRORBODY",
                }
            ).encode(),
            status_code=400,
            media_type="application/json",
        )

    upstream.responder = responder
    t = tokli()
    send(t)
    logs = t.logs.getvalue()
    assert "invalid_request_error" in logs and "bad field" in logs
    assert "TOKLI-CANARY-ERRORBODY" not in logs


def test_logs_never_contain_credentials(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    oauth = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=(FIXTURES / "string_content.json").read_bytes(),
        headers={**HEADERS, "authorization": "Bearer sk-ant-oat01-TOKLI-CANARY-OAUTH-SECRET"},
    )
    t.wait_trace(oauth.headers["x-tokli-request-id"])
    send(t)
    everything = (
        t.logs.getvalue()
        + json.dumps(db_rows(t, "requests"))
        + json.dumps(db_rows(t, "compressor_stats"))
    )
    db_bytes = (t.services.config.dirs.data_dir / "tokli.db").read_bytes()
    for secret in (KEY, "TOKLI-CANARY-OAUTH-SECRET"):
        assert secret not in everything
        assert secret.encode() not in db_bytes


def test_default_logging_contains_no_prompt_text(tokli: Start) -> None:
    t = tokli()
    responses = [send(t, name) for name in ALL]
    api = "".join(
        httpx.get(t.url + f"/tokli/api/requests/{r.headers['x-tokli-request-id']}").text
        for r in responses
    )
    everything = t.logs.getvalue() + api + json.dumps(db_rows(t, "requests"))
    db_bytes = (t.services.config.dirs.data_dir / "tokli.db").read_bytes()
    assert "TOKLI-CANARY" not in everything
    assert b"TOKLI-CANARY" not in db_bytes


def test_api_contract_schemas(tokli: Start) -> None:
    t = tokli()
    trace = trace_of(t, send(t))
    assert trace["api_version"] == 1
    assert set(trace) == {"api_version", "request_id", "trace", "record", "compressors"}
    missing = httpx.get(t.url + "/tokli/api/requests/01ZZZZZZZZZZZZZZZZZZZZZZZZ")
    assert missing.status_code == 404 and missing.json()["error"]["type"] == "not_found"


def test_every_api_token_field_has_method(tokli: Start) -> None:
    t = tokli()
    record = trace_of(t, send(t))["record"]
    for field in ("est_original_tokens", "est_forwarded_tokens"):
        assert record[field]["method"] == "estimate"
        assert isinstance(record[field]["value"], int)
    for field in ("usage_input", "usage_output", "usage_cache_read"):
        assert record[field] == {"value": None, "reason": "unavailable_until_s2"}


def test_api_returns_no_content_or_credentials(tokli: Start) -> None:
    t = tokli()
    text = "".join(json.dumps(trace_of(t, send(t, name))) for name in ALL)
    assert "TOKLI-CANARY" not in text


def test_trace_served_from_db_after_buffer_eviction(tokli: Start) -> None:
    t = tokli("observability.trace_buffer=1")
    first = send(t)
    send(t)
    trace = trace_of(t, first)
    assert trace["record"]["request_id"] == first.headers["x-tokli-request-id"]


def test_sink_failure_degrades_not_breaks(tokli: Start, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = data_dir / "tokli.db"
    sqlite3.connect(db).close()
    os.chmod(db, stat.S_IREAD)  # a read-only database file (AC-TC-6)
    try:
        t = tokli()
        assert send(t).status_code == 200
        assert send(t).status_code == 200
        assert t.services.store is not None
        t.services.store.flush()
        health = httpx.get(t.url + "/tokli/health").json()
        assert health["status"] == "degraded" and health["checks"]["telemetry"] == "failing"
        warnings = [line for line in t.log_lines() if '"WARNING"' in line and "telemetry" in line]
        assert len(warnings) == 1
    finally:
        os.chmod(db, stat.S_IREAD | stat.S_IWRITE)


def test_health_degraded_conditions(tokli: Start, monkeypatch: pytest.MonkeyPatch) -> None:
    t = tokli()
    monkeypatch.setitem(t.services.availability, "json_minify", "unavailable(missing_module)")  # type: ignore[arg-type]
    health = httpx.get(t.url + "/tokli/health").json()
    assert health["status"] == "degraded"
    assert health["checks"]["compressors"] == "unavailable: json_minify"


def test_no_outbound_connections_except_upstream(
    tokli: Start, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = tokli()
    original = socket.socket.connect
    attempts: list[object] = []

    def guarded(self: socket.socket, address: Any) -> None:
        attempts.append(address)
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"outbound connection to {address}")
        return original(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    for name in ALL:
        assert send(t, name).status_code == 200
    assert all(
        (a[0] if isinstance(a, tuple) else a) in ("127.0.0.1", "::1", "localhost") for a in attempts
    )


def test_telemetry_db_created_in_data_dir(tokli: Start) -> None:
    t = tokli()
    send(t)
    assert (t.services.config.dirs.data_dir / "tokli.db").is_file()
