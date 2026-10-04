"""SPEC 019 `reread_by_reference` end to end (S8e): the forwarded re-read carries notes, the
earlier read stays intact, and the default configuration leaves the request unchanged."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from tests.integration.servers import FakeUpstream, Tokli
from tests.unit.test_reread_by_reference import conversation, module, numbered

HEADERS = {"x-api-key": "sk-ant-api03-TOKLI-CANARY", "anthropic-version": "2023-06-01"}
Start = Callable[..., Tokli]


def send(t: Tokli, data: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=json.dumps(data).encode(),
        headers=HEADERS,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    return t.wait_trace(response.headers["x-tokli-request-id"])


def results(body: dict[str, Any]) -> list[str]:
    return [
        b["content"]
        for m in body["messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    ]


def edited() -> tuple[list[str], dict[str, Any]]:
    old = module(60)
    new = [*old[:30], "an inserted line", *old[30:]]
    return old, conversation(("read", old), ("edit", None), ("read", new))


def test_reread_by_reference_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-PR-20 through the proxy: the re-read is forwarded as notes plus the changed line."""
    # The request budget never skips a pruner (CC-014, S8f SCR-001), so it is left at its default.
    t = tokli("compressors.reread_by_reference.enabled=true")
    old, data = edited()
    trace = send(t, data)
    forwarded = results(json.loads(upstream.received[-1].body))
    assert forwarded[0] == numbered(old)
    assert forwarded[2].count("[tokli: lines ") == 2
    assert "    31\tan inserted line" in forwarded[2]
    stats = {c["compressor_id"]: c for c in trace["compressors"]}["reread_by_reference"]
    assert stats["accepted"] == 1
    assert trace["record"]["history_rewritten"] is False  # prefix-stable


def test_reread_by_reference_on_by_default(tokli: Start, upstream: FakeUpstream) -> None:
    """On by default since its smoke record (S8e P3); switched off, the request is unchanged."""
    t = tokli()
    _, data = edited()
    send(t, data)
    assert results(json.loads(upstream.received[-1].body))[2].count("[tokli: lines ") == 2
    off = tokli("compressors.reread_by_reference.enabled=false")
    send(off, data)
    assert results(json.loads(upstream.received[-1].body)) == results(data)
