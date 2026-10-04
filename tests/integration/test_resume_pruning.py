"""SPEC 019 `edit_args_on_resume` end to end (S8c): AC-PR-11…AC-PR-14, PR-023, PR-025; the
conversation state of ADR 0012 lives in the running Tokli."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import httpx

from tests.integration.servers import FakeUpstream, Tokli
from tests.unit.test_resume_pruning import FILE, body, human

HEADERS = {"x-api-key": "sk-ant-api03-TOKLI-CANARY", "anthropic-version": "2023-06-01"}
Start = Callable[..., Tokli]
# The request budget stays at its default: since S8f SCR-001 it never skips a pruner (CC-014).
# Before, a slow CI runner skipped this pruner on one request (macOS / 3.11, run 37228678522).
ON = ("compressors.edit_args_on_resume.enabled=true",)


def send(t: Tokli, data: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        t.url + "/anthropic/v1/messages",
        content=json.dumps(data).encode(),
        headers=HEADERS,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    return t.wait_trace(response.headers["x-tokli-request-id"])


def forwarded(upstream: FakeUpstream) -> dict[str, Any]:
    return json.loads(upstream.received[-1].body)


def write_content(data: dict[str, Any]) -> str:
    return data["messages"][1]["content"][0]["input"]["content"]


def call_ids(data: dict[str, Any]) -> list[str | None]:
    return [
        block.get("id") or block.get("tool_use_id")
        for message in data["messages"]
        if isinstance(message["content"], list)
        for block in message["content"]
    ]


def test_resume_pruning_stable_between_resumes(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-PR-11…AC-PR-13, PR-023, PR-025: the first request of an unknown conversation is a
    resume; a request a minute later forwards a byte-identical prefix and prunes nothing new;
    two hours later a newly old call is pruned."""
    t = tokli(*ON)
    now = [10_000.0]
    t.services.conversations.clock = lambda: now[0]

    first = body(turns_after_write=6, turns_after_edit=2)
    trace = send(t, first)
    sent_first = forwarded(upstream)
    assert write_content(sent_first).startswith("[tokli: earlier edit content omitted")
    assert trace["record"]["history_rewritten"] is True

    now[0] += 60
    second = copy.deepcopy(first)
    second["messages"][-1:-1] = [*human("one more"), *human("and another")]
    trace = send(t, second)
    sent_second = forwarded(upstream)
    shared = len(first["messages"]) - 1  # everything before the final question of the first
    assert sent_second["messages"][:shared] == sent_first["messages"][:shared]
    edit = next(
        m
        for m in sent_second["messages"]
        if m["role"] == "assistant"
        and isinstance(m["content"], list)
        and m["content"][0].get("id") == "toolu_e2"
    )
    assert not edit["content"][0]["input"]["old_string"].startswith(
        "[tokli:"
    )  # old now, but not a resume
    assert trace["record"]["history_rewritten"] is False

    now[0] += 7200
    trace = send(t, second)
    edit = next(
        m
        for m in forwarded(upstream)["messages"]
        if m["role"] == "assistant"
        and isinstance(m["content"], list)
        and m["content"][0].get("id") == "toolu_e2"
    )
    assert edit["content"][0]["input"]["old_string"].startswith(
        "[tokli: earlier edit content omitted"
    )
    assert trace["record"]["history_rewritten"] is True
    stats = {c["compressor_id"]: c for c in trace["compressors"]}["edit_args_on_resume"]
    assert stats["accepted"] == 3  # Write.content, Edit.old_string, Edit.new_string


def test_resume_pruning_off_by_default_end_to_end(tokli: Start, upstream: FakeUpstream) -> None:
    """AC-PR-14: with the default configuration the arguments are forwarded unchanged."""
    t = tokli()
    send(t, body())
    assert write_content(forwarded(upstream)) == FILE
    assert len(t.services.conversations) >= 0  # the store exists even when the pruner is off


def test_pruned_history_is_accepted_shape(tokli: Start, upstream: FakeUpstream) -> None:
    """PR-005 as changed: only the listed strings differ; the number, order and pairing of
    messages, tool calls and tool results are unchanged."""
    t = tokli(*ON)
    data = body()
    send(t, data)
    sent = forwarded(upstream)
    assert [m["role"] for m in sent["messages"]] == [m["role"] for m in data["messages"]]
    assert call_ids(sent) == call_ids(data)
