"""SPEC 019 `edit_args_on_resume` (S8c): PR-020…PR-026, AC-PR-11…AC-PR-16; SPEC 001 CM-009 and
SPEC 003 for argument segments; ADR 0012 (conversation key and store)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.helpers import FakeCounter, view_of
from tests.unit.test_engine import settings_for
from tokli.app.conversations import ConversationStore
from tokli.compression.engine import Engine
from tokli.compressors.edit_args_on_resume import SPEC, EditArgsOnResume
from tokli.domain.models import SegmentKind
from tokli.domain.stage import ConversationView
from tokli.protocols.anthropic_messages import conversation_key, parse, render

FIELDS = {
    "Write": ["content"],
    "Edit": ["old_string", "new_string"],
    "MultiEdit": ["edits/*/old_string", "edits/*/new_string"],
}
ALL_KINDS = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT, SegmentKind.TOOL_CALL_ARGS})
FILE = "".join(f"SETTING_{n} = {n * 7}  # synthetic configuration line {n}\n" for n in range(12))
OLD = "".join(f"    value_{n} = compute({n})  # old body line\n" for n in range(6))
NEW = "".join(f"    value_{n} = compute_fast({n})  # new body line\n" for n in range(6))


def tool_use(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": call_id, "name": name, "input": args}],
    }


def tool_result(call_id: str, text: str = "ok") -> dict[str, Any]:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": call_id, "content": text}],
    }


def human(text: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": text}, {"role": "assistant", "content": "Noted."}]


def body(
    turns_after_write: int = 6, turns_after_edit: int = 6, tool_only: int = 0
) -> dict[str, Any]:
    """Write config.py, then `turns_after_write - turns_after_edit` human turns, an Edit of
    app.py, then `turns_after_edit` human turns; `tool_only` extra tool-only exchanges after the
    edit (which are not human turns)."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Start the synthetic task."}]
    messages += [
        tool_use("toolu_w1", "Write", {"file_path": "config.py", "content": FILE}),
        tool_result("toolu_w1"),
    ]
    for n in range(turns_after_write - turns_after_edit):
        messages += human(f"between {n}")
    messages += [
        tool_use(
            "toolu_e2", "Edit", {"file_path": "src/app.py", "old_string": OLD, "new_string": NEW}
        ),
        tool_result("toolu_e2"),
    ]
    for n in range(tool_only):
        messages += [
            tool_use(f"toolu_t{n}", "Bash", {"command": "ls"}),
            tool_result(f"toolu_t{n}", "a\nb"),
        ]
    for n in range(turns_after_edit):
        messages += human(f"later {n}")
    messages.append({"role": "user", "content": "What next?"})
    return {
        "model": "claude-test",
        "max_tokens": 64,
        "system": "You are a synthetic agent.",
        "messages": messages,
    }


def prune(data: dict[str, Any], conversation: ConversationView | None, **options: Any):  # type: ignore[no-untyped-def]
    request = parse(json.dumps(data).encode(), mutable_kinds=ALL_KINDS, arg_fields=FIELDS)
    engine = Engine(
        [EditArgsOnResume(**options)], settings_for("edit_args_on_resume", min_segment_tokens=0)
    )
    result = engine.run(request, view_of(request), FakeCounter(), conversation)
    return request, result, json.loads(render(request, result.patches))


def stubbed_calls(request, result) -> set[str]:  # type: ignore[no-untyped-def]
    return {request.segment(p.segment_id).tool_call_id for p in result.patches}


# -- adapter: argument segments (CM-009, SPEC 003) -----------------------------------------


def test_argument_segments_only_for_listed_fields() -> None:
    raw = json.dumps(body()).encode()
    plain = parse(raw, mutable_kinds=ALL_KINDS)
    assert not [s for s in plain.segments if s.kind is SegmentKind.TOOL_CALL_ARGS]
    request = parse(raw, mutable_kinds=ALL_KINDS, arg_fields=FIELDS)
    args = [s for s in request.segments if s.kind is SegmentKind.TOOL_CALL_ARGS]
    assert {(s.tool_call_id, s.locator.rsplit("/", 1)[-1]) for s in args} == {
        ("toolu_w1", "content"),
        ("toolu_e2", "old_string"),
        ("toolu_e2", "new_string"),
    }
    assert all(s.mutable and s.tool_name in ("Write", "Edit") for s in args)
    assert all(s.locator.startswith("/messages/") and "/input/" in s.locator for s in args)
    not_mutable = parse(raw, mutable_kinds=frozenset({SegmentKind.TOOL_RESULT}), arg_fields=FIELDS)
    assert not any(s.mutable for s in not_mutable.segments if s.kind is SegmentKind.TOOL_CALL_ARGS)


def test_multiedit_wildcard_fields() -> None:
    data = body()
    edits = [{"old_string": OLD, "new_string": NEW}, {"old_string": "a", "new_string": "b"}]
    data["messages"].insert(
        -1, tool_use("toolu_m3", "MultiEdit", {"file_path": "x.py", "edits": edits})
    )
    data["messages"].insert(-1, tool_result("toolu_m3"))
    request = parse(json.dumps(data).encode(), mutable_kinds=ALL_KINDS, arg_fields=FIELDS)
    locators = sorted(
        s.locator.split("/input/")[1]
        for s in request.segments
        if s.tool_call_id == "toolu_m3" and s.kind is SegmentKind.TOOL_CALL_ARGS
    )
    assert locators == [
        "edits/0/new_string",
        "edits/0/old_string",
        "edits/1/new_string",
        "edits/1/old_string",
    ]


def test_human_turn_definition() -> None:
    """PR-026: a human turn is a user message with human text; tool-only messages, and messages
    that mix tool results with text (for example injected reminders), are not."""
    data = body(turns_after_write=3, turns_after_edit=1, tool_only=5)
    mixed = {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "toolu_t0", "content": "x"},
            {"type": "text", "text": "<system-reminder>r</system-reminder>"},
        ],
    }
    data["messages"].insert(-1, mixed)
    request = parse(json.dumps(data).encode(), mutable_kinds=ALL_KINDS, arg_fields=FIELDS)
    turns = {t.call_id: t.human_turns_after for t in request.tools}
    assert turns["toolu_w1"] == 4  # 2 between + 1 later + the final question
    assert turns["toolu_e2"] == 2  # 1 later + the final question
    assert turns["toolu_t0"] == 2


def test_conversation_key() -> None:
    """ADR 0012: the key depends only on `system` and the first message."""
    a = parse(json.dumps(body(turns_after_edit=2)).encode(), mutable_kinds=ALL_KINDS)
    b = parse(json.dumps(body(turns_after_edit=5)).encode(), mutable_kinds=ALL_KINDS)
    other = body()
    other["messages"][0] = {"role": "user", "content": "A different task."}
    c = parse(json.dumps(other).encode(), mutable_kinds=ALL_KINDS)
    assert len(conversation_key(a)) == 64 and conversation_key(a) == conversation_key(b)
    assert conversation_key(a) != conversation_key(c)


# -- the pruner (PR-020…PR-023, PR-026) ---------------------------------------------------


def test_resume_pruning_keeps_structure_and_paths() -> None:
    """AC-PR-11: at a resume the listed strings become stubs; keys, file paths, ids, order and
    every other value stay the same."""
    data = body()
    request, result, forwarded = prune(data, ConversationView(7200.0))
    assert stubbed_calls(request, result) == {"toolu_w1", "toolu_e2"}
    write = forwarded["messages"][1]["content"][0]
    assert write["id"] == "toolu_w1" and write["input"]["file_path"] == "config.py"
    assert write["input"]["content"] == (
        f"[tokli: earlier edit content omitted ({len(FILE)} tokens) — "
        "read the file for its current state]"
    )
    restored = json.loads(json.dumps(forwarded))
    restored["messages"][1]["content"][0]["input"]["content"] = FILE
    edit_index = next(
        i
        for i, m in enumerate(restored["messages"])
        if m["role"] == "assistant"
        and isinstance(m["content"], list)
        and m["content"][0].get("id") == "toolu_e2"
    )
    restored["messages"][edit_index]["content"][0]["input"].update(old_string=OLD, new_string=NEW)
    assert restored == data


def test_resume_pruning_only_at_resume_and_old_calls() -> None:
    """AC-PR-11, AC-PR-16: nothing before `resume_after_s`; only calls followed by at least
    `resume_min_age_turns` human turns; tool-only messages do not count; short strings stay."""
    data = body(turns_after_write=6, turns_after_edit=2, tool_only=6)
    _, before, _ = prune(data, ConversationView(3599.0))
    assert before.patches == ()
    request, after, _ = prune(data, ConversationView(3601.0))
    assert stubbed_calls(request, after) == {"toolu_w1"}  # the Edit has 3 human turns after it
    request, small, _ = prune(data, ConversationView(3601.0), min_tokens=10_000)
    assert small.patches == ()


def test_unknown_conversation_is_resume() -> None:
    """AC-PR-13 (S8c review P5): an unknown conversation, or none at all, is a resume."""
    for conversation in (ConversationView(None), None):
        request, result, _ = prune(body(), conversation)
        assert stubbed_calls(request, result) == {"toolu_w1", "toolu_e2"}


def test_resume_pruning_reapplies_stored_set_between_resumes() -> None:
    """PR-023: between resumes exactly the stored calls are pruned, even if other calls became
    old meanwhile."""
    request, result, _ = prune(body(), ConversationView(60.0, frozenset({"toolu_w1"})))
    assert stubbed_calls(request, result) == {"toolu_w1"}
    request, result, _ = prune(body(), ConversationView(60.0, frozenset()))
    assert result.patches == ()


def test_resume_pruning_off_by_default() -> None:
    """AC-PR-14, PR-020: SELECTIVE, request scope, not prefix-stable, off by default."""
    from tokli.config.schema import TokliSettings

    assert (SPEC.kind, SPEC.scope, SPEC.prefix_stable, SPEC.default_enabled) == (
        "SELECTIVE",
        "request",
        False,
        False,
    )
    assert TokliSettings().compressors.edit_args_on_resume.enabled is False


# -- the conversation store (PR-024) ------------------------------------------------------


def test_conversation_store_bounded_and_memory_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-PR-15: bounded with least-recently-used eviction; nothing is written to disk."""
    monkeypatch.chdir(tmp_path)
    now = [1000.0]
    store = ConversationStore(capacity=2, clock=lambda: now[0])
    assert store.view("a").seconds_since_last is None
    assert store.record("a", {"toolu_1"}) is True  # newly pruned: history rewritten
    now[0] += 30
    view = store.view("a")
    assert view.seconds_since_last == 30 and view.pruned_call_ids == {"toolu_1"}
    assert store.record("a", {"toolu_1"}) is False  # the same set again
    store.record("b", ())
    store.view("a")  # a is now the most recently used
    store.record("c", ())
    assert len(store) == 2 and store.view("b").seconds_since_last is None
    assert os.listdir(tmp_path) == []
