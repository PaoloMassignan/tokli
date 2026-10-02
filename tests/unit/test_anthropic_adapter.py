"""SPEC 001 / SPEC 003 (S1): Anthropic Messages parsing and patch-based rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tokli.domain.models import MUTABLE_ELIGIBLE, Patch, SegmentKind
from tokli.protocols.anthropic_messages import ParseError, parse, render

FIXTURES = Path(__file__).resolve().parents[1] / "compat" / "fixtures" / "anthropic_messages"
ALL = sorted(p.stem for p in FIXTURES.glob("*.json"))
DEFAULT_KINDS = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT})


def raw(name: str) -> bytes:
    return (FIXTURES / f"{name}.json").read_bytes()


def resolve(document: Any, pointer: str) -> Any:
    node = document
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def changed_pointers(a: Any, b: Any, path: str = "") -> set[str]:
    if type(a) is not type(b):
        return {path}
    if isinstance(a, dict):
        if list(a) != list(b):
            return {path}
        return set().union(*(changed_pointers(a[k], b[k], f"{path}/{k}") for k in a))
    if isinstance(a, list):
        if len(a) != len(b):
            return {path}
        return set().union(
            *(
                changed_pointers(x, y, f"{path}/{i}")
                for i, (x, y) in enumerate(zip(a, b, strict=True))
            )
        )
    return set() if a == b else {path}


@pytest.mark.parametrize("name", ALL)
def test_passthrough_forwards_original_bytes(name: str) -> None:
    request = parse(raw(name), mutable_kinds=DEFAULT_KINDS)
    assert render(request, []) == raw(name)
    # patches that change nothing also keep the original bytes
    same = [Patch(s.id, s.text, ("noop",)) for s in request.segments if s.mutable]
    assert render(request, same) == raw(name)


@pytest.mark.parametrize("name", ALL)
def test_render_changes_only_patched_values(name: str) -> None:
    request = parse(raw(name), mutable_kinds=DEFAULT_KINDS)
    patches = [Patch(s.id, f"<patched {s.id}>", ("dummy",)) for s in request.segments if s.mutable]
    rendered = render(request, patches)
    before, after = json.loads(raw(name)), json.loads(rendered)
    assert changed_pointers(before, after) == {
        request.segment(p.segment_id).locator for p in patches
    }
    for patch in patches:
        assert resolve(after, request.segment(patch.segment_id).locator) == patch.new_text


def shape(node: Any) -> Any:
    """Structure with every string replaced: types, keys, block counts and order."""
    if isinstance(node, dict):
        return {k: shape(v) for k, v in node.items()}
    if isinstance(node, list):
        return [shape(v) for v in node]
    return "<str>" if isinstance(node, str) else node


@pytest.mark.parametrize("name", ALL)
def test_structure_preserved_after_compression(name: str) -> None:
    request = parse(raw(name), mutable_kinds=DEFAULT_KINDS)
    patches = [
        Patch(s.id, s.text[: len(s.text) // 2], ("dummy",)) for s in request.segments if s.mutable
    ]
    assert shape(json.loads(render(request, patches))) == shape(json.loads(raw(name)))


def test_patched_body_utf8_and_length() -> None:
    request = parse(raw("unicode_and_numbers"), mutable_kinds=DEFAULT_KINDS)
    segment = next(s for s in request.segments if s.mutable)
    rendered = render(request, [Patch(segment.id, "Café — 漢字 😀", ("dummy",))])
    assert "Café — 漢字 😀".encode() in rendered  # non-ASCII is not escaped
    assert json.loads(rendered)["temperature"] == 0.7
    assert json.loads(rendered)["top_p"] == 0.1


def test_anthropic_segment_mapping() -> None:
    request = parse(raw("tool_use_and_results"), mutable_kinds=DEFAULT_KINDS)
    kinds = [(s.kind, s.locator, s.mutable) for s in request.segments]
    assert kinds == [
        (SegmentKind.TOOL_DESCRIPTION, "/tools/0/description", False),
        (SegmentKind.TOOL_DESCRIPTION, "/tools/1/description", False),
        (SegmentKind.USER_TEXT, "/messages/0/content", True),
        (SegmentKind.ASSISTANT_TEXT, "/messages/1/content/0/text", False),
        (SegmentKind.TOOL_RESULT, "/messages/2/content/0/content", True),
        (SegmentKind.TOOL_RESULT, "/messages/2/content/1/content/0/text", True),
        (SegmentKind.TOOL_RESULT, "/messages/4/content/0/content/0/text", True),
        (SegmentKind.TOOL_RESULT, "/messages/4/content/1/content", True),
        (SegmentKind.USER_TEXT, "/messages/4/content/2/text", True),
    ]
    assert [s.id for s in request.segments] == [f"s{i}" for i in range(len(request.segments))]
    assert [s.index for s in request.segments] == list(range(len(request.segments)))
    assert request.model == "claude-sonnet-4-5" and request.stream is True


def test_system_segments() -> None:
    kinds = [
        (s.kind, s.locator, s.mutable)
        for s in parse(raw("system_string"), mutable_kinds=DEFAULT_KINDS).segments
    ]
    assert kinds[0] == (SegmentKind.SYSTEM, "/system", False)
    blocks = parse(raw("blocks_with_cache_control"), mutable_kinds=DEFAULT_KINDS).segments
    assert [(s.kind, s.locator) for s in blocks[:2]] == [
        (SegmentKind.SYSTEM, "/system/0/text"),
        (SegmentKind.SYSTEM, "/system/1/text"),
    ]


def test_anthropic_tool_name_resolution() -> None:
    request = parse(raw("tool_use_and_results"), mutable_kinds=DEFAULT_KINDS)
    results = [s for s in request.segments if s.kind is SegmentKind.TOOL_RESULT]
    assert [(s.tool_name, s.tool_call_id) for s in results] == [
        ("mcp__tracker__get_issue", "toolu_01A"),
        ("Read", "toolu_01B"),
        ("mcp__tracker__get_issue", "toolu_01C"),
        (None, "toolu_UNKNOWN"),  # no matching tool_use: no guess (AC-AN-2)
    ]


def test_anthropic_block_attributes_preserved() -> None:
    request = parse(raw("tool_use_and_results"), mutable_kinds=DEFAULT_KINDS)
    results = [s for s in request.segments if s.kind is SegmentKind.TOOL_RESULT]
    assert [s.is_error for s in results] == [False, False, True, False]
    assert [s.cache_breakpoint_after for s in results] == [False, False, True, False]
    patches = [Patch(s.id, "x", ("dummy",)) for s in request.segments if s.mutable]
    after = json.loads(render(request, patches))
    block = after["messages"][4]["content"][0]
    assert block["is_error"] is True and block["tool_use_id"] == "toolu_01C"
    assert block["content"][0]["cache_control"] == {"type": "ephemeral"}


def count_cache_control(node: Any) -> int:
    if isinstance(node, dict):
        return ("cache_control" in node) + sum(count_cache_control(v) for v in node.values())
    if isinstance(node, list):
        return sum(count_cache_control(v) for v in node)
    return 0


@pytest.mark.parametrize("name", ALL)
def test_anthropic_cache_control_count_preserved(name: str) -> None:
    request = parse(raw(name), mutable_kinds=DEFAULT_KINDS)
    patches = [Patch(s.id, "x", ("dummy",)) for s in request.segments if s.mutable]
    assert count_cache_control(json.loads(render(request, patches))) == count_cache_control(
        json.loads(raw(name))
    )


def test_unknown_block_types_roundtrip() -> None:
    request = parse(raw("unknown_future_parts"), mutable_kinds=DEFAULT_KINDS)
    assert [(s.kind, s.locator) for s in request.segments] == [
        (SegmentKind.USER_TEXT, "/messages/0/content/1/text")
    ]
    rendered = json.loads(render(request, [Patch("s0", "changed", ("dummy",))]))
    original = json.loads(raw("unknown_future_parts"))
    assert rendered["x_future"] == original["x_future"]
    assert rendered["messages"][0]["content"][0] == original["messages"][0]["content"][0]


@pytest.mark.parametrize("name", ALL)
def test_forbidden_parts_never_mutable(name: str) -> None:
    every_kind = frozenset(SegmentKind)
    for segment in parse(raw(name), mutable_kinds=every_kind).segments:
        assert segment.mutable == (segment.kind in MUTABLE_ELIGIBLE)


def test_opaque_parts_not_exposed() -> None:
    texts = [
        s.text for s in parse(raw("thinking_and_signatures"), mutable_kinds=DEFAULT_KINDS).segments
    ]
    assert not any("TOKLI-CANARY-THINK" in t for t in texts)
    images = [
        s.locator for s in parse(raw("images_and_documents"), mutable_kinds=DEFAULT_KINDS).segments
    ]
    assert images == ["/messages/0/content/2/text"]


def test_mutable_kinds_from_config() -> None:
    only_results = parse(
        raw("tool_use_and_results"), mutable_kinds=frozenset({SegmentKind.TOOL_RESULT})
    )
    assert {s.kind for s in only_results.segments if s.mutable} == {SegmentKind.TOOL_RESULT}


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[1, 2]",
        b'{"model": "x"}',
        b'{"messages": "nope"}',
        b'{"messages": [1]}',
        b"\xff\xfe",
    ],
)
def test_malformed_body_raises_parse_error(body: bytes) -> None:
    with pytest.raises(ParseError):
        parse(body, mutable_kinds=DEFAULT_KINDS)
