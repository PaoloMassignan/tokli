"""SPEC 019 `reread_by_reference` (S8e): PR-030…PR-036, AC-PR-20…AC-PR-26; ADR 0013."""

from __future__ import annotations

import dataclasses
import json
import time
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import FakeCounter, view_of
from tests.unit.test_engine import Fake, settings_for
from tokli.compression.contract import SegmentRef, SegmentView
from tokli.compression.engine import Engine
from tokli.compressors.reread_by_reference import SPEC, RereadByReference
from tokli.domain.models import SegmentKind, Span
from tokli.protocols.anthropic_messages import parse, render

KINDS = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT})
ARG_KINDS = KINDS | {SegmentKind.TOOL_CALL_ARGS}


def numbered(lines: list[str], first: int = 1) -> str:
    return "\n".join(f"{n:>6}\t{line}" for n, line in enumerate(lines, start=first))


def module(size: int = 30, tag: str = "a") -> list[str]:
    return [f"line {n} of the synthetic module {tag} = value_{n}" for n in range(1, size + 1)]


def call(call_id: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": call_id, "name": name, "input": args}],
    }


def result(call_id: str, text: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": call_id, "content": text}],
    }


def conversation(*steps: tuple[str, Any], path: str = "src/mod.py") -> dict[str, Any]:
    """Steps: ("read", lines) · ("write", lines) · ("edit", None)."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Start the synthetic task."}]
    for n, (kind, payload) in enumerate(steps):
        cid = f"toolu_{kind[0]}{n}"
        if kind == "read":
            messages += [call(cid, "Read", {"file_path": path}), result(cid, numbered(payload))]
        elif kind == "write":
            messages += [
                call(cid, "Write", {"file_path": path, "content": "\n".join(payload) + "\n"}),
                result(cid, "File created."),
            ]
        else:
            messages += [
                call(cid, "Edit", {"file_path": path, "old_string": "x", "new_string": "y"}),
                result(cid, "The file has been updated."),
            ]
    messages.append({"role": "user", "content": "What next?"})
    return {"model": "claude-test", "max_tokens": 64, "messages": messages}


def run(data: dict[str, Any], *extra, kinds=KINDS, spans=None, verbatim=None, **options: Any):  # type: ignore[no-untyped-def]
    request = parse(
        json.dumps(data).encode(),
        mutable_kinds=kinds,
        arg_fields={"Write": ["content"]} if kinds is ARG_KINDS else None,
    )
    engine = Engine(
        [RereadByReference(**options), *extra],
        settings_for(
            "reread_by_reference",
            *(c.spec.id for c in extra),
            min_segment_tokens=0,
            **({} if verbatim is None else {"verbatim_tools": verbatim}),
        ),
    )
    outcome = engine.run(request, view_of(request, spans=spans), FakeCounter())
    return request, outcome, json.loads(render(request, outcome.patches))


def results(forwarded: dict[str, Any]) -> list[str]:
    return [
        b["content"]
        for m in forwarded["messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    ]


def test_reread_notes_after_edit() -> None:
    """AC-PR-20: the changed line stays; unchanged runs become notes with shifted ranges."""
    old = module(30)
    new = [*old[:10], "an inserted line", *old[10:]]
    _, _outcome, forwarded = run(conversation(("read", old), ("edit", None), ("read", new)))
    assert results(forwarded)[2] == "\n".join(
        [
            "[tokli: lines 1-10 unchanged — identical to lines 1-10 of the read in call toolu_r0]",
            "    11\tan inserted line",
            "[tokli: lines 12-31 unchanged — identical to lines 11-30 "
            "of the read in call toolu_r0]",
        ]
    )
    assert results(forwarded)[0] == numbered(old)  # the source is untouched


def test_reread_source_write() -> None:
    """AC-PR-21: a `Write` of the same path is a source; the note says "content written"."""
    written = module(20, "w")
    read = [*written[:5], "a changed line", *written[6:]]
    _, _, forwarded = run(conversation(("write", written), ("read", read)))
    text = results(forwarded)[1]
    assert text.startswith(
        "[tokli: lines 1-5 unchanged — identical to lines 1-5 "
        "of the content written in call toolu_w0]"
    )
    assert "     6\ta changed line" in text


def test_reread_not_applicable_reasons() -> None:
    """AC-PR-22: no source, no run, other numbering, too large: unchanged, with the reason."""

    def reasons(data: dict[str, Any], **options: Any) -> dict[str, int]:
        _, outcome, _ = run(data, **options)
        stats = next(s for s in outcome.stats if s.compressor_id == "reread_by_reference")
        return dict(stats.skip_reasons)

    assert "not_applicable(no_source)" in reasons(conversation(("read", module(20))))
    old, new = module(20, "a"), module(20, "b")
    assert "not_applicable(no_run)" in reasons(conversation(("read", old), ("read", new)))
    arrows = conversation(("read", module(20)), ("read", module(20)))
    arrows["messages"][4]["content"][0]["content"] = "\n".join(
        f"{n}→{x}" for n, x in enumerate(module(20), 1)
    )
    assert "not_applicable(nonstandard_numbering)" in reasons(arrows)
    assert "not_applicable(too_large)" in reasons(
        conversation(("read", module(20)), ("read", module(20))), max_lines=10
    )


def test_reread_never_chains_notes() -> None:
    """AC-PR-23 (PR-033): read3 refers to read1, never to the referenced read2."""
    v1 = module(30)
    v2 = [*v1[:5], "change one", *v1[6:]]
    v3 = [*v2[:20], "change two", *v2[21:]]
    _, _, forwarded = run(
        conversation(("read", v1), ("edit", None), ("read", v2), ("edit", None), ("read", v3))
    )
    third = results(forwarded)[4]
    assert "toolu_r0" in third and "toolu_r2" not in third


def test_reread_source_integrity_enforced() -> None:
    """AC-PR-24 (CC-019): a later compressor that would change a source is rejected."""
    old = module(30)
    new = [*old[:10], "an inserted line", *old[10:]]
    shrink = Fake(cid="zz_shrink", kind="SELECTIVE", transform=lambda t: t[: len(t) // 2])
    shrink.spec = dataclasses.replace(
        shrink.spec,
        stage="semantic",
        equivalence="none",
        segment_kinds=frozenset({SegmentKind.TOOL_RESULT}),
    )
    # Without verbatim tools, so that the shrinking compressor really reaches the source.
    _, outcome, forwarded = run(
        conversation(("read", old), ("edit", None), ("read", new)), shrink, verbatim=frozenset()
    )
    assert results(forwarded)[0] == numbered(old)
    rejected = [
        i
        for i in outcome.invocations
        if i.compressor_id == "zz_shrink" and i.decision == "rejected"
    ]
    assert any(i.reason == "reference_target_modified" for i in rejected)


def test_reread_keeps_reminders_and_verbatim_tool() -> None:
    """AC-PR-25 (PR-036): an appended reminder stays verbatim; `Read`, a verbatim tool, is
    handled."""
    old = module(30)
    reminder = "<system-reminder>\nA synthetic reminder.\n</system-reminder>"
    data = conversation(("read", old), ("edit", None), ("read", [*old[:3], "x", *old[4:]]))
    text = data["messages"][6]["content"][0]["content"] + "\n\n" + reminder
    data["messages"][6]["content"][0]["content"] = text
    request = parse(json.dumps(data).encode(), mutable_kinds=KINDS)
    sid = next(s.id for s in request.segments if s.tool_call_id == "toolu_r2")
    start = text.index(reminder)
    _, _outcome, forwarded = run(
        data, spans={sid: [Span(start, start + len(reminder), "system_reminder")]}
    )
    assert results(forwarded)[2].endswith("\n\n" + reminder)
    assert "[tokli: lines" in results(forwarded)[2]


def test_reread_linear_time() -> None:
    """AC-PR-26 (PR-035): one changed line in 5,000 vs 50,000 lines: time ratio at most 15."""

    def elapsed(size: int) -> float:
        old = [f"row {n}: payload {n * 7}" for n in range(size)]
        new = [*old[: size // 2], "the changed row", *old[size // 2 + 1 :]]
        data = conversation(("read", old), ("edit", None), ("read", new))
        request = parse(json.dumps(data).encode(), mutable_kinds=KINDS)
        refs = [
            SegmentRef(
                s.id,
                SegmentView(s.kind, s.role, s.tool_name, s.is_error, ()),
                s.tool_call_id,
                s.whole_result,
            )
            for s in request.segments
            if s.mutable and s.kind is SegmentKind.TOOL_RESULT
        ]
        texts = {s.id: s.text for s in request.segments}
        from tokli.compression.contract import ToolRecordView

        tools = [ToolRecordView(t.call_id, t.name, t.arguments) for t in request.tools]
        pruner = RereadByReference(max_lines=10**6)
        best = float("inf")
        for _ in range(3):
            started = time.perf_counter()
            proposals = pruner.plan(refs, texts, tools, len, None)
            best = min(best, time.perf_counter() - started)
        assert any(p.new_text for p in proposals)
        return best

    elapsed(1000)
    assert elapsed(50_000) / max(elapsed(5_000), 1e-6) <= 15


def test_reread_prefix_stable_across_turns() -> None:
    """PR-004 for this pruner: the forwarded body of turn N is a prefix of turn N+1's."""
    old = module(30)
    new = [*old[:10], "an inserted line", *old[10:]]
    turn = conversation(("read", old), ("edit", None), ("read", new))
    later = conversation(
        ("read", old),
        ("edit", None),
        ("read", new),
        ("edit", None),
        ("read", [*new[:2], "z", *new[3:]]),
    )
    _, _, first = run(turn)
    _, _, second = run(later)
    shared = len(turn["messages"]) - 1
    assert second["messages"][:shared] == first["messages"][:shared]


def test_reread_on_by_default_and_declared() -> None:
    from tokli.config.schema import TokliSettings

    assert (SPEC.kind, SPEC.equivalence, SPEC.prefix_stable, SPEC.default_enabled) == (
        "LOSSLESS",
        "reference",
        True,
        True,  # on by default after its smoke record (S8e P3)
    )
    assert TokliSettings().compressors.reread_by_reference.enabled is True


# -- whole-request decode (CC-015 for `reference`) ------------------------------------------

EDIT = st.tuples(
    st.sampled_from(["insert", "delete", "replace"]), st.integers(0, 39), st.integers(0, 9)
)


@settings(max_examples=120, deadline=None)
@given(st.lists(EDIT, min_size=1, max_size=4), st.booleans(), st.integers(5, 40))
def prop_reread_by_reference_decodes_whole_request(
    edits: list[tuple[str, int, int]], start_with_write: bool, size: int
) -> None:
    """Whatever the edits between reads, replacing every note with the source lines it names
    rebuilds each original result exactly (and a `Write` source too)."""
    lines = [f"v{n % 7} common line {n % 5}" for n in range(size)]
    steps: list[tuple[str, Any]] = [("write" if start_with_write else "read", list(lines))]
    for kind, at, value in edits:
        at = at % max(1, len(lines))
        if kind == "insert":
            lines.insert(at, f"inserted {value}")
        elif kind == "delete" and len(lines) > 1:
            del lines[at]
        else:
            lines[at] = f"replaced {value}"
        steps += [("edit", None), ("read", list(lines))]
    data = conversation(*steps)
    request, outcome, _ = run(data, kinds=ARG_KINDS)
    texts = {s.id: s.text for s in request.segments}
    for patch in outcome.patches:
        texts[patch.segment_id] = patch.new_text
    refs = [
        SegmentRef(
            s.id,
            SegmentView(s.kind, s.role, s.tool_name, s.is_error, ()),
            s.tool_call_id,
            s.whole_result,
        )
        for s in request.segments
        if s.mutable
    ]
    decoded = RereadByReference().decode_request(texts, refs)
    for segment in request.segments:
        if segment.mutable:
            assert decoded[segment.id] == segment.text
