"""SPEC 019 `outline_first_read` end to end (S8j): the first read of a code file is forwarded as
its skeleton, a later read whole, with a stable prefix (PR-040…PR-046)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from tests.integration.servers import FakeUpstream, Tokli
from tests.unit.test_outline_first_read import PY_TEXT, SHELL_NOTE, body, call, py_outline, result

HEADERS = {"x-api-key": "sk-ant-api03-TOKLI-CANARY", "anthropic-version": "2023-06-01"}
Start = Callable[..., Tokli]
ON = ("compressors.outline_first_read.enabled=true", "pruning.outline_min_tokens=0")


def send(t: Tokli, data: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=json.dumps(data).encode(),
        headers=HEADERS,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    return t.wait_trace(response.headers["x-tokli-request-id"])


def tool_results(data: dict[str, Any]) -> list[str]:
    return [
        b["content"]
        for m in data["messages"]
        if isinstance(m["content"], list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    ]


def test_outline_first_read_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """The first `cat` of a module is forwarded as its skeleton; the next request, which reads it
    again, forwards the same prefix and the second read whole; nothing is rewritten."""
    t = tokli(*ON)
    first = body(("Bash", {"command": "cat src/a.py"}, PY_TEXT))
    trace = send(t, first)
    sent_first = json.loads(upstream.received[-1].body)
    assert tool_results(sent_first) == [py_outline(SHELL_NOTE)]
    assert trace["record"]["history_rewritten"] is False
    stats = {c["compressor_id"]: c for c in trace["compressors"]}["outline_first_read"]
    assert stats["accepted"] == 1

    second = json.loads(json.dumps(first))
    second["messages"][-1:] = [
        {"role": "user", "content": "I need the body of load_harbor."},
        call("toolu_9", "Bash", {"command": "cat src/a.py"}),
        result("toolu_9", PY_TEXT),
        {"role": "user", "content": "What next?"},
    ]
    trace = send(t, second)
    sent_second = json.loads(upstream.received[-1].body)
    shared = len(first["messages"]) - 1
    assert sent_second["messages"][:shared] == sent_first["messages"][:shared]
    assert tool_results(sent_second) == [py_outline(SHELL_NOTE), PY_TEXT]
    assert trace["record"]["history_rewritten"] is False


def test_outline_first_read_off_by_default_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-PR-27: with the default configuration the read is forwarded whole."""
    t = tokli()
    send(t, body(("Bash", {"command": "cat src/a.py"}, PY_TEXT)))
    assert tool_results(json.loads(upstream.received[-1].body)) == [PY_TEXT]
