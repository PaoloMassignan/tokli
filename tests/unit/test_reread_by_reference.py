"""SPEC 019 `reread_by_reference` (S8e): PR-030…PR-036, AC-PR-20…AC-PR-26; ADR 0013."""

from __future__ import annotations

import dataclasses
import gc
import json
import time
from typing import Any

import pytest
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


def numbered(lines: list[str], first: int = 1, style: str = "padded6") -> str:
    """`padded6` is `cat -n`; `plain` is what Claude Code's `Read` really sends (S8h)."""
    if style == "plain":
        return "\n".join(f"{n}\t{line}" for n, line in enumerate(lines, start=first))
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


def conversation(
    *steps: tuple[str, Any], path: str = "src/mod.py", style: str = "padded6"
) -> dict[str, Any]:
    """Steps: ("read", lines) · ("write", lines) · ("edit", None)."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "Start the synthetic task."}]
    for n, (kind, payload) in enumerate(steps):
        cid = f"toolu_{kind[0]}{n}"
        if kind == "read":
            messages += [
                call(cid, "Read", {"file_path": path}),
                result(cid, numbered(payload, style=style)),
            ]
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
    """AC-PR-24 (CC-019 after S6 SCR-001): a later compressor that changes a source is kept, and
    the notes naming it are reverted; no note names a changed source."""
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
    source, _, reread = results(forwarded)
    assert source == numbered(old)[: len(numbered(old)) // 2]  # the earlier change wins
    assert "[tokli:" not in reread  # the notes were reverted, then the shrink applied
    assert outcome.reference_stubs == 0
    reverted = [i for i in outcome.invocations if i.reason == "reference_target_changed"]
    assert [i.compressor_id for i in reverted] == ["reread_by_reference"]


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
    """AC-PR-26 (PR-035): one changed line in 5,000 vs 50,000 lines: time ratio at most 15.

    The best of 7 runs with the garbage collector paused measures the algorithm itself. With the
    best of 3 and the collector on, macOS CI runners measured 17.8x and 18.1x (S8f CI run
    37233467737), while the cost per line is flat from 5,000 to 200,000 lines (1.5 to 2.0 us
    locally): the 6 ms denominator was dominated by runner noise."""

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
        gc.collect()
        gc.disable()
        try:
            for _ in range(7):
                started = time.perf_counter()
                proposals = pruner.plan(refs, texts, tools, len, None)
                best = min(best, time.perf_counter() - started)
        finally:
            gc.enable()
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


def test_reread_stays_when_a_later_read_duplicates_it() -> None:
    """Regression (found by the S6 E2 dry run; S6 SCR-001). Root cause: a later read identical
    to an earlier re-read is stubbed first by `duplicate_tool_results`, which makes the re-read a
    reference target; CC-019 / PR-012 then reject `reread_by_reference` on it. The re-read was
    sent as notes on the previous request and is sent whole on this one: history already sent
    changes, and the provider rewrites its cache from there. The decision for a segment must
    not depend on a later segment (PR-004)."""
    from tokli.compressors.duplicate_tool_results import DuplicateToolResults

    old = module(30)
    new = [*old[:10], "an inserted line", *old[10:]]
    turn = conversation(("read", old), ("edit", None), ("read", new))
    later = conversation(("read", old), ("edit", None), ("read", new), ("read", new))
    _, _, first = run(turn, DuplicateToolResults(0, False))
    _, outcome, second = run(later, DuplicateToolResults(0, False))
    shared = len(turn["messages"]) - 1
    assert results(first)[2].startswith("[tokli: lines")  # the re-read was sent as notes
    assert second["messages"][:shared] == first["messages"][:shared]
    # AC-CC-16: the later identical read is compressed too (second pass), not sent whole
    assert results(second)[3].startswith("[tokli: lines")
    reasons = {(i.compressor_id, i.reason) for i in outcome.invocations if i.decision == "rejected"}
    assert ("duplicate_tool_results", "reference_target_changed") in reasons


@settings(max_examples=60, deadline=None)
@given(st.lists(st.sampled_from(["read", "edit"]), min_size=2, max_size=7), st.randoms())
def prop_history_stays_stable_with_both_reference_compressors(steps: list[str], rnd: Any) -> None:
    """AC-CC-16 (CC-019, PR-004): whatever the sequence of reads and edits, the forwarded history
    of each turn is unchanged in the next turn, with both reference compressors on."""
    from tokli.compressors.duplicate_tool_results import DuplicateToolResults

    lines = module(30)
    history: list[tuple[str, Any]] = []
    previous: dict[str, Any] | None = None
    for step in steps:
        if step == "edit":
            at = rnd.randrange(len(lines))
            lines = [*lines[:at], f"edited line {at}", *lines[at + 1 :]]
            history.append(("edit", None))
        else:
            history.append(("read", list(lines)))
        data = conversation(*history)
        _, _, forwarded = run(data, DuplicateToolResults(0, False))
        if previous is not None:
            shared = len(previous["messages"]) - 1  # the old last message is the old question
            assert forwarded["messages"][:shared] == previous["messages"][:shared]
        previous = forwarded


def test_reread_applies_to_claude_code_numbering() -> None:
    """Regression (S8h SCR-001). Root cause: PR-032 accepted only the `cat -n` prefix
    `"{n:>6}\t"`, but Claude Code's `Read` numbers lines as `"{n}\t"` with no padding, so every
    real re-read was rejected as `nonstandard_numbering` and the compressor never acted on real
    traffic (0 applicable of 1,627 considered on the human's dogfood)."""
    old = module(30)
    new = [*old[:10], "an inserted line", *old[10:]]
    data = conversation(("read", old), ("edit", None), ("read", new), style="plain")
    _, outcome, forwarded = run(data)
    reread = results(forwarded)[2]
    assert reread.startswith("[tokli: lines 1-10 unchanged")
    assert "\n11\tan inserted line\n" in "\n" + reread + "\n"  # kept in the result's own style
    assert not any(line.startswith("    11\t") for line in reread.split("\n"))
    assert outcome.reference_stubs == 1


def test_reread_mixed_numbering_unchanged() -> None:
    """PR-032 (S8h): a result mixing the two styles is not changed."""
    old = module(12)
    mixed = numbered(old[:6], style="plain") + "\n" + numbered(old[6:], first=7)
    data = conversation(("read", old), ("edit", None), ("read", old), style="plain")
    data["messages"][6]["content"][0]["content"] = mixed
    _, outcome, forwarded = run(data)
    assert results(forwarded)[2] == mixed
    reasons = [i.reason for i in outcome.invocations if i.compressor_id == "reread_by_reference"]
    assert "not_applicable(nonstandard_numbering)" in reasons


@pytest.mark.parametrize("style", ["padded6", "plain"])
def test_reread_from_write_keeps_its_numbering_recoverable(style: str) -> None:
    """PR-032 (S8h): a `Write` source carries no numbering style. When every line of the re-read
    would become a note, the first numbered line stays verbatim, so the result's own style is
    recoverable and decoding rebuilds it exactly."""
    lines = module(20)
    data = conversation(("write", lines), ("read", lines), style=style, path="src/new.py")
    request, outcome, forwarded = run(data, kinds=ARG_KINDS)
    reread = results(forwarded)[1]
    first = numbered(lines[:1], style=style)
    assert reread.startswith(first + "\n[tokli: lines 2-20 unchanged")
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
    original = {s.id: s.text for s in request.segments}
    assert all(decoded[sid] == original[sid] for sid in original if sid in decoded)


def test_reread_on_by_default_and_declared() -> None:
    from tokli.config.schema import TokliSettings

    assert (SPEC.kind, SPEC.equivalence, SPEC.prefix_stable, SPEC.version) == (
        "LOSSLESS",
        "reference",
        True,
        "2",  # S8h SCR-001: Claude Code's numbering changes its output
    )
    # On by default with its version 2 smoke record (2026-10-09; CC-020; S8h).
    assert SPEC.default_enabled is True
    assert TokliSettings().compressors.reread_by_reference.enabled is True


# -- whole-request decode (CC-015 for `reference`) ------------------------------------------

EDIT = st.tuples(
    st.sampled_from(["insert", "delete", "replace"]), st.integers(0, 39), st.integers(0, 9)
)


@settings(max_examples=160, deadline=None)
@given(
    st.lists(EDIT, min_size=0, max_size=4),
    st.booleans(),
    st.integers(5, 40),
    st.sampled_from(["padded6", "plain"]),
)
def prop_reread_by_reference_decodes_whole_request(
    edits: list[tuple[str, int, int]], start_with_write: bool, size: int, style: str
) -> None:
    """Whatever the edits between reads, and in both numbering styles (S8h), replacing every
    note with the source lines it names rebuilds each original result exactly (and a `Write`
    source too)."""
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
    steps.append(("read", list(lines)))  # an unchanged re-read: every line can become a note
    data = conversation(*steps, style=style)
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
