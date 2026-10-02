"""S1 acceptance 1 and 2 over the Anthropic compat corpus (AC-CM-1, AC-AN-1, CP-JM-001…004)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.integration.servers import FakeUpstream, Tokli

FIXTURES = Path(__file__).resolve().parents[1] / "compat" / "fixtures" / "anthropic_messages"
ALL = sorted(p.stem for p in FIXTURES.glob("*.json"))
HEADERS = {"x-api-key": "sk-ant-api03-TOKLI-CANARY-KEY", "anthropic-version": "2023-06-01"}
Start = Callable[..., Tokli]


def send(tokli: Tokli, content: bytes) -> httpx.Response:
    return httpx.post(
        tokli.url + "/anthropic/v1/messages", content=content, headers=HEADERS, timeout=10
    )


def leaves(node: Any, path: str = "") -> dict[str, Any]:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            out.update(leaves(v, f"{path}/{k}"))
        return out
    if isinstance(node, list):
        out = {}
        for i, v in enumerate(node):
            out.update(leaves(v, f"{path}/{i}"))
        return out
    return {path: node}


def test_passthrough_forwards_original_bytes(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli("compressors.json_minify.enabled=false")
    for name in ALL:
        content = (FIXTURES / f"{name}.json").read_bytes()
        assert send(t, content).status_code == 200
        assert upstream.received[-1].body == content, name


@pytest.mark.parametrize("name", ALL)
def test_only_json_tool_results_of_non_verbatim_tools_change(
    tokli: Start, upstream: FakeUpstream, name: str
) -> None:
    content = (FIXTURES / f"{name}.json").read_bytes()
    send(tokli(), content)
    before, after = json.loads(content), json.loads(upstream.received[-1].body)
    before_leaves, after_leaves = leaves(before), leaves(after)
    assert before_leaves.keys() == after_leaves.keys()  # structure identical
    changed = [p for p in before_leaves if before_leaves[p] != after_leaves[p]]
    for pointer in changed:
        original, forwarded = before_leaves[pointer], after_leaves[pointer]
        assert "/content" in pointer  # only tool results / user text values
        assert json.loads(original) == json.loads(forwarded)  # round-trips
        assert len(forwarded) < len(original)


def test_expected_changes_in_tool_use_fixture(tokli: Start, upstream: FakeUpstream) -> None:
    content = (FIXTURES / "tool_use_and_results.json").read_bytes()
    send(tokli(), content)
    after = json.loads(upstream.received[-1].body)
    before = json.loads(content)
    user = after["messages"][2]["content"]
    assert user[0]["content"] != before["messages"][2]["content"][0]["content"]  # MCP JSON minified
    assert user[1] == before["messages"][2]["content"][1]  # Read (verbatim tool) untouched
    last = after["messages"][4]["content"]
    assert (
        last[0]["content"][0]["text"] != before["messages"][4]["content"][0]["content"][0]["text"]
    )
    assert last[1] == before["messages"][4]["content"][1]  # unresolved tool: untouched (CC-023)


def test_claude_code_like_reminders_protected(tokli: Start, upstream: FakeUpstream) -> None:
    content = (FIXTURES / "claude_code_like.json").read_bytes()
    send(tokli(), content)
    after = json.loads(upstream.received[-1].body)
    before = json.loads(content)
    # JSON + trailing reminder is not solely JSON: untouched; Bash is a verbatim tool: untouched
    assert after["messages"][2]["content"][0] == before["messages"][2]["content"][0]
    assert after["messages"][2]["content"][1] == before["messages"][2]["content"][1]
    assert after == before


def test_prose_only_request_passthrough(tokli: Start, upstream: FakeUpstream) -> None:
    t = tokli()
    content = (FIXTURES / "string_content.json").read_bytes()
    response = send(t, content)
    assert upstream.received[-1].body == content
    trace = t.wait_trace(response.headers["x-tokli-request-id"])
    assert trace["record"]["outcome"] == "passthrough"
    assert trace["record"]["passthrough_reason"] in {"no_applicable_compressor", "no_gain"}


class UpperUserText:
    """A test-only transformer: uppercases USER_TEXT segments (PL-007)."""

    id = "transform.upper"
    kind = "transformer"

    def run(self, request, view, ctx):  # type: ignore[no-untyped-def]
        from tokli.domain.models import Patch, SegmentKind
        from tokli.domain.stage import StageResult

        return StageResult(
            patches=[
                Patch(s.id, view.texts[s.id].upper(), (self.id,))
                for s in request.segments
                if s.mutable and s.kind is SegmentKind.USER_TEXT
            ]
        )


def test_new_transformer_through_adapter_end_to_end(tmp_path: Path, upstream: FakeUpstream) -> None:
    from dataclasses import replace

    from tests.integration.servers import BYTE_CATALOG, make_config, run_tokli
    from tokli.app.bootstrap import bootstrap
    from tokli.pipeline.pipeline import Pipeline
    from tokli.pipeline.reminders import RemindersStage

    config = make_config(tmp_path, upstream.url)
    services = replace(
        bootstrap(config, catalog=BYTE_CATALOG, version="test"),
        pipeline=Pipeline([RemindersStage(), UpperUserText()]),  # type: ignore[list-item]
    )
    with run_tokli(config, services) as t:
        for name in ALL:
            content = (FIXTURES / f"{name}.json").read_bytes()
            send(t, content)
            before, after = (
                leaves(json.loads(content)),
                leaves(json.loads(upstream.received[-1].body)),
            )
            assert before.keys() == after.keys()
            for pointer, value in before.items():
                if after[pointer] != value:
                    assert after[pointer] == value.upper(), (name, pointer)
