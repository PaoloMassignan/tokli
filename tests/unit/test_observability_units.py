"""OB-001, OB-003, OB-004, OB-007 units: ULIDs, trace buffer bound, reason codes, redaction."""

from __future__ import annotations

import io
import json
import logging
import re

from tokli.auth.passthrough import (
    credential_kind,
    forward_request_headers,
    header_names,
    hop_by_hop,
)
from tokli.observability import reasons
from tokli.observability.ids import new_request_id
from tokli.observability.logs import configure_logging, log_fields, redact
from tokli.observability.trace import Trace, TraceBuffer


def test_request_ids_are_ulids_and_sortable() -> None:
    ids = [new_request_id(now_ms=1_700_000_000_000 + i) for i in range(50)]
    assert all(re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", i) for i in ids)
    assert ids == sorted(ids)
    assert len(set(new_request_id() for _ in range(1000))) == 1000


def test_trace_buffer_bounded() -> None:
    buffer = TraceBuffer(capacity=500)
    for i in range(10_000):
        buffer.add(f"id{i}", {"n": i})
    assert len(buffer) == 500
    assert buffer.get("id0") is None and buffer.get("id9999") == {"n": 9999}


def test_trace_to_dict() -> None:
    trace = Trace(request_id="R", started=10.0)
    trace.span("parse", 10.001, 10.003, segments=3)
    trace.decide("route", "known_endpoint")
    data = trace.to_dict()
    assert data["request_id"] == "R"
    assert data["spans"][0]["name"] == "parse" and round(data["spans"][0]["ms"], 3) == 2.0
    assert round(data["spans"][0]["offset_ms"], 3) == 1.0 and data["spans"][0]["attrs"] == {
        "segments": 3
    }
    assert data["decisions"] == [{"decision": "route", "reason": "known_endpoint"}]


def test_reason_codes_known() -> None:
    for code in (
        "known_endpoint",
        "too_small",
        "not_applicable(not_json)",
        "unavailable(x)",
        "stage_exception(transform.compression)",
        "upstream_status(429)",
        "verbatim_tool(unresolved)",
    ):
        assert reasons.is_known(code), code
    for code in ("made_up", "tooSmall", "not_applicable", "(x)"):
        assert reasons.is_known(code) == (code == "not_applicable"), code


def test_redaction_masks_credentials() -> None:
    text = (
        "key sk-ant-api03-abcdefghijkl and Bearer sk-ant-oat01-xyz123456 and x-api-key: secret123"
    )
    masked = redact(text)
    for secret in ("sk-ant-api03-abcdefghijkl", "sk-ant-oat01-xyz123456", "secret123"):
        assert secret not in masked
    assert "[redacted]" in masked


def test_json_log_line_is_structured_and_redacted() -> None:
    stream = io.StringIO()
    handler = configure_logging("json", stream=stream)
    try:
        log_fields(
            logging.getLogger("tokli.request"),
            logging.INFO,
            "request",
            event="request",
            request_id="R1",
            note="sk-ant-api03-SHOULDNOTAPPEAR",
        )
    finally:
        logging.getLogger().removeHandler(handler)
    line = json.loads(stream.getvalue().strip())
    assert line["event"] == "request" and line["request_id"] == "R1" and line["level"] == "INFO"
    assert "SHOULDNOTAPPEAR" not in stream.getvalue()


def test_hop_by_hop_includes_connection_listed() -> None:
    headers = [("Connection", "keep-alive, X-Private"), ("X-Private", "1"), ("X-Keep", "2")]
    assert "x-private" in hop_by_hop(headers)
    assert forward_request_headers([*headers, ("Host", "h"), ("Content-Length", "3")]) == [
        ("X-Keep", "2")
    ]


def test_credential_kind_classification() -> None:
    assert credential_kind([("x-api-key", "sk-ant-api03-x")]) == "api_key"
    assert credential_kind([("authorization", "Bearer sk-ant-oat01-x")]) == "oauth"
    assert credential_kind([("Authorization", "Bearer sk-ant-api03-x")]) == "api_key"
    assert credential_kind([("authorization", "Bearer something")]) == "unknown"
    assert credential_kind([("content-type", "application/json")]) == "none"


def test_header_names_only() -> None:
    names = header_names([("X-Api-Key", "secret"), ("content-type", "a"), ("x-api-key", "again")])
    assert names == ["content-type", "x-api-key"]


def test_policy_forbids_removed_from_closed_set() -> None:
    """S4 SCR-001: kinds no longer gate execution, so `policy_forbids` is never produced."""
    assert not reasons.is_known("policy_forbids(LOSSY)")
