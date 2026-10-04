"""``search_group``: group consecutive grep lines of one path under a ``[file]`` header
(SPEC 010, CP-SG-001…004). LOSSLESS, byte equivalence.

Format: a run of ≥ 2 consecutive grep lines with the same path becomes ``[file] <path>``
followed by one ``  <line>:<content>`` line per match. Every other line stays in place; a line
that the decoder would read as format (``[file] …``, ``\\…``, ``  <digits>:…``) is escaped with a
leading ``\\``. Lines are split on ``\\n`` with their endings kept; the header takes the ending
of its group's first line.
"""

from __future__ import annotations

import re

from tokli.compression.contract import Applicability, CompressorSpec, SegmentView
from tokli.compression.text_shapes import parse_grep_line, split_lines
from tokli.domain.models import SegmentKind
from tokli.domain.stage import Features

SPEC = CompressorSpec(
    id="search_group",
    name="Search grouping",
    version="2",  # S8a SCR-003: timestamps and space-containing paths are no longer grouped
    kind="LOSSLESS",
    equivalence="byte",
    scope="segment",
    prefix_stable=True,
    guarantees=(
        "byte round-trip (prop_search_group_decode_roundtrip)",
        "unparsed lines stay in place (test_search_group_keeps_unparsed_lines_in_place)",
    ),
    assumptions=("reads_grouped_search", "not_quoted_verbatim"),
    stage="structural",
    segment_kinds=frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT}),
    min_tokens=0,
    cost_class="cheap",
    terminal=False,
    requires=(),
    default_enabled=False,
)

_HEADER = "[file] "
_MEMBER = re.compile(r"  [0-9]+:")


def _ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n" if line.endswith("\n") else ""


def _needs_escape(line: str) -> bool:
    return line.startswith((_HEADER, "\\")) or _MEMBER.match(line) is not None


def _groups(
    parsed: list[tuple[str, str] | None],
) -> list[tuple[int, int]]:
    """``(first, last)`` index of every run of ≥ 2 consecutive grep lines with one path."""
    runs: list[tuple[int, int]] = []
    i, n = 0, len(parsed)
    while i < n:
        entry = parsed[i]
        if entry is None:
            i += 1
            continue
        j = i
        while j + 1 < n and (following := parsed[j + 1]) is not None and following[0] == entry[0]:
            j += 1
        if j > i:
            runs.append((i, j))
        i = j + 1
    return runs


class SearchGroup:
    spec = SPEC

    def __init__(self, min_group_lines: int = 5) -> None:
        self._min_group_lines = min_group_lines

    def _plan(self, text: str) -> tuple[list[str], list[tuple[str, str] | None], str]:
        """Lines, their grep parse, and an empty reason when the text should be grouped."""
        lines = split_lines(text)
        parsed = [parse_grep_line(line) for line in lines]
        if sum(1 for p in parsed if p is not None) < self._min_group_lines:
            return lines, parsed, "too_few_grep_lines"
        return lines, parsed, ""

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability:
        if features.grep_lines < self._min_group_lines:
            return Applicability(False, "too_few_grep_lines")  # routing feature (RT-002)
        _, parsed, reason = self._plan(text)
        if reason:
            return Applicability(False, reason)
        if not _groups(parsed):
            return Applicability(False, "no_group")
        return Applicability(True)

    def compress(self, text: str, view: SegmentView) -> str | None:
        lines, parsed, reason = self._plan(text)
        runs = _groups(parsed) if not reason else []
        if not runs:
            return None
        out: list[str] = []
        position = 0
        for first, last in runs:
            out.extend(
                "\\" + line if _needs_escape(line) else line for line in lines[position:first]
            )
            entry = parsed[first]
            assert entry is not None  # a run starts on a grep line
            out.append(_HEADER + entry[0] + _ending(lines[first]))
            for index in range(first, last + 1):
                member = parsed[index]
                assert member is not None
                out.append("  " + member[1])
            position = last + 1
        out.extend("\\" + line if _needs_escape(line) else line for line in lines[position:])
        return "".join(out)

    def decode(self, text: str) -> str:
        lines = split_lines(text)
        out: list[str] = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            if line.startswith("\\"):
                out.append(line[1:])
                i += 1
            elif line.startswith(_HEADER):
                path = line[len(_HEADER) : len(line) - len(_ending(line))]
                i += 1
                while i < n and _MEMBER.match(lines[i]):
                    out.append(path + ":" + lines[i][2:])
                    i += 1
            else:
                out.append(line)
                i += 1
        return "".join(out)

    def equivalent(self, original: str, decoded: str) -> bool:
        return original == decoded
