"""S8i SCR-001: a resume follows the cache lifetime the client asked for.

SPEC 003 AN-011 (AC-AN-7); SPEC 019 PR-021, PR-024, PR-027 (AC-PR-17, AC-PR-18); ADR 0012
amendment 1."""

from __future__ import annotations

import itertools
import json
from typing import Any

import pytest

from tokli.app.conversations import ConversationStore
from tokli.domain.models import SegmentKind
from tokli.domain.stage import ConversationView
from tokli.protocols.anthropic_messages import parse, render

PROTOCOL = "anthropic_messages"
KEY = "synthetic-conversation"
KINDS = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT})
NO_MARKER = object()
FIVE_MIN_TTLS: tuple[Any, ...] = (None, "5m")  # None: a marker without `ttl`


def marker(ttl: Any) -> dict[str, Any]:
    return {"type": "ephemeral"} if ttl is None else {"type": "ephemeral", "ttl": ttl}


def body(system: Any = NO_MARKER, tool: Any = NO_MARKER, message: Any = NO_MARKER) -> bytes:
    """A synthetic request with an optional `cache_control` marker in `system`, `tools` and a
    message block (each argument is a ttl, None for a marker without ttl, NO_MARKER for none)."""
    system_block: dict[str, Any] = {"type": "text", "text": "You are a synthetic agent."}
    tool_def: dict[str, Any] = {
        "name": "Lookup",
        "description": "Looks something up.",
        "input_schema": {"type": "object", "properties": {"cache_control": {"type": "string"}}},
    }
    text_block: dict[str, Any] = {"type": "text", "text": "TOKLI-CANARY question"}
    for target, ttl in ((system_block, system), (tool_def, tool), (text_block, message)):
        if ttl is not NO_MARKER:
            target["cache_control"] = marker(ttl)
    data = {
        "model": "claude-test",
        "max_tokens": 16,
        "system": [system_block],
        "tools": [tool_def],
        "messages": [
            {"role": "user", "content": "Start."},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Lookup",
                        # opaque input: a field named cache_control here is not a marker
                        "input": {"cache_control": {"type": "ephemeral", "ttl": "24h"}},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "found"},
                    text_block,
                ],
            },
        ],
    }
    return json.dumps(data).encode()


def lifetime(ttl: Any) -> int | None:
    if ttl is NO_MARKER:
        return None
    return 3600 if ttl == "1h" else 300


# -- the adapter (AN-011, AC-AN-7) ----------------------------------------------------------


@pytest.mark.parametrize("places", list(itertools.product((NO_MARKER, None, "5m", "1h"), repeat=3)))
def test_adapter_exposes_cache_ttl(places: tuple[Any, Any, Any]) -> None:
    """AC-AN-7: markers in `system`, `tools` and a message block, with `ttl` absent, "5m" and
    "1h" in every combination → the longest lifetime; no marker → absent. The forwarded body is
    unchanged."""
    raw = body(*places)
    request = parse(raw, mutable_kinds=KINDS)
    known = [lifetime(ttl) for ttl in places if ttl is not NO_MARKER]
    assert request.cache_ttl_s == (max(known) if known else None)  # type: ignore[type-var]
    assert request.cache_ttl_unrecognised is False
    assert render(request, []) == raw


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "ephemeral", "ttl": "24h"},
        {"type": "persistent"},
        {"type": "ephemeral", "ttl": 3600},
        "ephemeral",
    ],
)
def test_adapter_unrecognised_cache_marker_leaves_ttl_absent(bad: Any) -> None:
    """AC-AN-7, AC-PR-18: a marker with another `ttl` or `type`, beside a known one → no
    lifetime, and the request is flagged for the `cache_ttl_unrecognised` trace."""
    data = json.loads(body(system="1h"))
    data["messages"][2]["content"][1]["cache_control"] = bad
    raw = json.dumps(data).encode()
    request = parse(raw, mutable_kinds=KINDS)
    assert request.cache_ttl_s is None
    assert request.cache_ttl_unrecognised is True
    assert render(request, []) == raw


def test_adapter_reads_markers_inside_tool_results() -> None:
    """AN-011: a marker on a text block inside a `tool_result` counts like any message block."""
    data = json.loads(body())
    data["messages"][2]["content"][0]["content"] = [
        {"type": "text", "text": "found", "cache_control": marker("1h")}
    ]
    assert parse(json.dumps(data).encode(), mutable_kinds=KINDS).cache_ttl_s == 3600


# -- the resume decision (PR-021, PR-024, PR-027) -------------------------------------------


def seen_after(
    previous_ttl: int | None,
    seconds: float,
    defaults: dict[str, float] | None = None,
    margin_s: float = 60.0,
) -> ConversationView:
    """The view of a conversation whose previous request carried `previous_ttl`, `seconds`
    after that request."""
    now = [50_000.0]
    store = ConversationStore(
        capacity=8,
        clock=lambda: now[0],
        ttl_defaults=defaults if defaults is not None else {PROTOCOL: 3600.0},
        margin_s=margin_s,
    )
    store.record(KEY, (), cache_ttl_s=previous_ttl)
    now[0] += seconds
    return store.view(KEY, PROTOCOL)


def test_resume_uses_previous_request_ttl_1h() -> None:
    """AC-PR-17 (as corrected by SCR-002): `ttl: "1h"` → 3,661 s is a resume, 3,660 s is not."""
    assert seen_after(3600, 3661).is_resume is True
    view = seen_after(3600, 3660)
    assert view.is_resume is False
    assert (view.cache_ttl_s, view.cache_ttl_source) == (3600, "previous_request")
    assert view.seconds_since_last == 3660


def test_resume_uses_previous_request_ttl_5m() -> None:
    """AC-PR-17: markers without `ttl` (300 s) → 361 s is a resume, 360 s is not; the protocol
    default (3,600 s) does not apply when the previous request stated a lifetime."""
    assert seen_after(300, 361).is_resume is True
    view = seen_after(300, 360)
    assert view.is_resume is False
    assert (view.cache_ttl_s, view.cache_ttl_source) == (300, "previous_request")


def test_resume_longest_ttl_wins() -> None:
    """AC-PR-18: a request with markers "5m" and "1h" has a lifetime of 3,600 s, so the next
    request 10 minutes later is not a resume."""
    request = parse(body(system="5m", message="1h"), mutable_kinds=KINDS)
    assert request.cache_ttl_s == 3600
    assert seen_after(request.cache_ttl_s, 600).is_resume is False


def test_resume_without_cache_marker_uses_protocol_default() -> None:
    """AC-PR-18, PR-027: no lifetime on the previous request → the protocol's default."""
    request = parse(body(), mutable_kinds=KINDS)
    assert request.cache_ttl_s is None
    view = seen_after(request.cache_ttl_s, 3660)
    assert view.is_resume is False
    assert (view.cache_ttl_s, view.cache_ttl_source) == (3600, "protocol_default")
    assert seen_after(None, 3661).is_resume is True
    assert seen_after(None, 181, defaults={PROTOCOL: 120.0}).is_resume is True
    assert seen_after(None, 180, defaults={PROTOCOL: 120.0}).is_resume is False


def test_resume_margin_is_configurable() -> None:
    """PR-021: the margin is `pruning.resume_margin_s`."""
    assert seen_after(300, 301, margin_s=0).is_resume is True
    assert seen_after(300, 300, margin_s=0).is_resume is False


def test_unknown_conversation_view() -> None:
    """PR-021, PR-028: an unknown conversation is a resume, with no time since its previous
    request."""
    store = ConversationStore(capacity=2, ttl_defaults={PROTOCOL: 3600.0}, margin_s=60.0)
    view = store.view("never-seen", PROTOCOL)
    assert view.is_resume is True
    assert view.seconds_since_last is None
    assert view.cache_ttl_source == "unknown_conversation"


def test_store_keeps_ttl_of_last_request_only() -> None:
    """PR-024: the store keeps the last request's lifetime, replacing the earlier one."""
    now = [0.0]
    store = ConversationStore(
        capacity=2, clock=lambda: now[0], ttl_defaults={PROTOCOL: 3600.0}, margin_s=60.0
    )
    store.record(KEY, (), cache_ttl_s=3600)
    now[0] += 100
    store.record(KEY, (), cache_ttl_s=300)
    now[0] += 400
    assert store.view(KEY, PROTOCOL).is_resume is True
