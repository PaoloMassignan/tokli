"""``reread_by_reference``: a re-read of a file keeps its changed lines and refers to the latest
original earlier copy (a read or a ``Write``) for the unchanged runs (SPEC 019 PR-030…PR-036,
ADR 0013). LOSSLESS by reference, prefix-stable.

A result is a block of ``cat -n`` lines (``"{n:>6}\\t<content>"``, consecutive numbers), with any
other lines (for example an appended ``<system-reminder>``) before or after it. Each run of at
least ``min_run_lines`` lines whose contents equal, in order, lines of the source becomes one
note; decoding puts the source lines back with their numbers.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from tokli.compression.contract import CompressorSpec, Proposal, SegmentRef, ToolRecordView
from tokli.domain.models import SegmentKind
from tokli.domain.stage import ConversationView

SPEC = CompressorSpec(
    id="reread_by_reference",
    name="Re-read by reference",
    version="1",
    kind="LOSSLESS",
    equivalence="reference",
    scope="request",
    prefix_stable=True,
    guarantees=(
        "whole-request decode restores every result "
        "(prop_reread_by_reference_decodes_whole_request)",
        "sources stay intact (test_reread_source_integrity_enforced)",
        "prefix-stable (test_reread_prefix_stable_across_turns)",
    ),
    assumptions=("reads_partial_reference", "quotes_from_reference_target"),
    stage="structural",
    segment_kinds=frozenset({SegmentKind.TOOL_RESULT, SegmentKind.TOOL_CALL_ARGS}),
    min_tokens=0,
    cost_class="cheap",
    terminal=True,
    requires=(),
    default_enabled=True,  # smoke record no_measurable_damage, 2026-10-04 (CC-020)
)

_NUMBERED = re.compile(r"^ *(\d+)\t")
_NOTE = re.compile(
    r"^\[tokli: lines (\d+)-(\d+) unchanged — identical to lines (\d+)-(\d+) of the "
    r"(read|content written) in call (\S+)\]$"
)


def normalise_path(path: str) -> str:
    """SPEC 019 path normalisation, with no filesystem access."""
    path = path.strip().strip("\"'").replace("\\", "/")
    path = re.sub(r"/{2,}", "/", path)
    path = re.sub(r"(^|/)\./", r"\1", path)
    if len(path) >= 2 and path[1] == ":":
        path = path[0].lower() + path[1:]
    return path


@dataclass(frozen=True)
class _Block:
    """A result split into the lines before, the numbered lines, and the lines after."""

    before: list[str]
    first: int
    lines: list[str]  # contents, without the number prefix
    after: list[str]


def _block(text: str) -> _Block | None:
    """The numbered block of a result, or ``None`` when numbering is not the standard one."""
    rows = text.split("\n")
    start = next((i for i, row in enumerate(rows) if _NUMBERED.match(row)), None)
    if start is None:
        return None
    end = start
    first = int(_NUMBERED.match(rows[start]).group(1))  # type: ignore[union-attr]
    contents: list[str] = []
    while end < len(rows):
        expected = f"{first + len(contents):>6}\t"
        if not rows[end].startswith(expected):
            break
        contents.append(rows[end][len(expected) :])
        end += 1
    if any(_NUMBERED.match(row) for row in rows[end:]):
        return None  # numbered lines out of sequence: not the standard numbering
    return _Block(rows[:start], first, contents, rows[end:])


def _write_lines(content: str) -> list[str]:
    lines = content.split("\n")
    return lines[:-1] if content.endswith("\n") else lines


def _note(a: int, b: int, c: int, d: int, kind: str, call_id: str) -> str:
    return (
        f"[tokli: lines {a}-{b} unchanged — identical to lines {c}-{d} "
        f"of the {kind} in call {call_id}]"
    )


@dataclass(frozen=True)
class _Source:
    call_id: str
    kind: str  # "read" or "content written"
    first: int
    lines: list[str]
    target_id: str | None  # the segment that holds it, when there is one


class RereadByReference:
    spec = SPEC

    def __init__(
        self,
        tools: Sequence[str] = ("Read",),
        min_run_lines: int = 5,
        max_lines: int = 20_000,
    ) -> None:
        self._tools = frozenset(tools)
        self._min_run = min_run_lines
        self._max_lines = max_lines

    def plan(
        self,
        refs: Sequence[SegmentRef],
        texts: Mapping[str, str],
        tools: Sequence[ToolRecordView],
        count: Callable[[str], int],
        conversation: ConversationView | None = None,
    ) -> list[Proposal]:
        records = {t.call_id: t for t in tools}
        order = {t.call_id: i for i, t in enumerate(tools)}
        args_segment = {
            r.call_id: r.segment_id
            for r in refs
            if r.view.kind is SegmentKind.TOOL_CALL_ARGS and r.call_id is not None
        }
        latest: dict[str, _Source] = {}
        changed: set[str] = set()  # results this pruner changes: never sources (PR-033)
        proposals: list[Proposal] = []
        results = [r for r in refs if r.view.kind is SegmentKind.TOOL_RESULT and r.call_id]
        # A Write is a source from its call on; results follow their call in document order.
        writes = sorted(
            (t for t in tools if t.name == "Write" and isinstance(t.arguments, dict)),
            key=lambda t: order[t.call_id],
        )
        pending_writes = list(writes)
        for ref in results:
            record = records.get(ref.call_id or "")
            if record is None:
                continue
            while pending_writes and order[pending_writes[0].call_id] < order[record.call_id]:
                self._add_write(pending_writes.pop(0), latest, texts, args_segment)
            if record.name not in self._tools or not isinstance(record.arguments, dict):
                continue
            path = record.arguments.get("file_path")
            if not isinstance(path, str) or not ref.whole_result:
                continue
            key = normalise_path(path)
            text = texts[ref.segment_id]
            block = _block(text)
            if block is None:
                proposals.append(Proposal(ref.segment_id, None, reason="nonstandard_numbering"))
                continue
            source = latest.get(key)
            if source is None:
                proposals.append(Proposal(ref.segment_id, None, reason="no_source"))
            elif max(len(block.lines), len(source.lines)) > self._max_lines:
                proposals.append(Proposal(ref.segment_id, None, reason="too_large"))
            else:
                new_text = self._replace(block, source)
                if new_text is None:
                    proposals.append(Proposal(ref.segment_id, None, reason="no_run"))
                else:
                    proposals.append(Proposal(ref.segment_id, new_text, source.target_id))
                    changed.add(ref.segment_id)
            if ref.segment_id not in changed and not ref.view.is_error:
                latest[key] = _Source(
                    record.call_id, "read", block.first, block.lines, ref.segment_id
                )
        return proposals

    def _add_write(
        self,
        record: ToolRecordView,
        latest: dict[str, _Source],
        texts: Mapping[str, str],
        args_segment: Mapping[str, str],
    ) -> None:
        args = record.arguments
        path, content = args.get("file_path"), args.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            return
        segment = args_segment.get(record.call_id)
        if segment is not None and texts.get(segment) != content:
            return  # changed by another pruner: not original any more
        latest[normalise_path(path)] = _Source(
            record.call_id, "content written", 1, _write_lines(content), segment
        )

    def _replace(self, block: _Block, source: _Source) -> str | None:
        matcher = SequenceMatcher(None, source.lines, block.lines, autojunk=False)
        runs = [m for m in matcher.get_matching_blocks() if m.size >= self._min_run]
        if not runs:
            return None
        out = list(block.before)
        position = 0
        for run in runs:
            for offset in range(position, run.b):
                out.append(f"{block.first + offset:>6}\t{block.lines[offset]}")
            a, b = block.first + run.b, block.first + run.b + run.size - 1
            c, d = source.first + run.a, source.first + run.a + run.size - 1
            out.append(_note(a, b, c, d, source.kind, source.call_id))
            position = run.b + run.size
        for offset in range(position, len(block.lines)):
            out.append(f"{block.first + offset:>6}\t{block.lines[offset]}")
        out += block.after
        return "\n".join(out)

    def decode_request(
        self, texts: Mapping[str, str], refs: Sequence[SegmentRef]
    ) -> dict[str, str]:
        """Replaces every note with the source lines it names (ADR 0013)."""
        sources: dict[str, tuple[int, list[str]]] = {}
        for ref in refs:
            if ref.call_id is None:
                continue
            if ref.view.kind is SegmentKind.TOOL_CALL_ARGS:
                sources[f"content written:{ref.call_id}"] = (1, _write_lines(texts[ref.segment_id]))
        decoded = dict(texts)
        for ref in refs:  # document order: a source is decoded before what refers to it
            if ref.view.kind is not SegmentKind.TOOL_RESULT:
                continue
            text = decoded[ref.segment_id]
            if "[tokli: lines " in text:
                text = self._expand(text, sources)
                decoded[ref.segment_id] = text
            block = _block(text) if ref.call_id else None
            if block is not None and ref.call_id is not None:
                sources[f"read:{ref.call_id}"] = (block.first, block.lines)
        return decoded

    @staticmethod
    def _expand(text: str, sources: Mapping[str, tuple[int, list[str]]]) -> str:
        out: list[str] = []
        for row in text.split("\n"):
            match = _NOTE.match(row)
            source = sources.get(f"{match.group(5)}:{match.group(6)}") if match else None
            if match is None or source is None:
                out.append(row)
                continue
            a, c, d = int(match.group(1)), int(match.group(3)), int(match.group(4))
            first, lines = source
            for offset, line in enumerate(lines[c - first : d - first + 1]):
                out.append(f"{a + offset:>6}\t{line}")
        return "\n".join(out)
