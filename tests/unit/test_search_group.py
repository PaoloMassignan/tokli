"""SPEC 010 `search_group` (S8a-1): CP-SG-001…004, review A8, reason codes, linear time."""

from __future__ import annotations

import gc
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import FakeCounter
from tokli.compression.contract import SegmentView
from tokli.compression.engine import _features
from tokli.compressors.search_group import SPEC, SearchGroup
from tokli.domain.models import SegmentKind

VIEW = SegmentView(SegmentKind.TOOL_RESULT, "user", "Grep", False, ())
GROUP = SearchGroup()


def applicability(text: str, compressor: SearchGroup = GROUP):  # type: ignore[no-untyped-def]
    return compressor.applicable(text, VIEW, _features(text, FakeCounter()))


def roundtrip(text: str) -> str | None:
    out = GROUP.compress(text, VIEW)
    if out is not None:
        assert GROUP.decode(out) == text
    return out


SAMPLE = (
    "Found 7 matches\n"
    "src/app/core.py:12:def load(path):\n"
    "src/app/core.py:40:    return load(path)\n"
    "src/app/core.py:41:    # load again\n"
    "--\n"
    "tests/test_core.py:7:from app.core import load\n"
    "tests/test_core.py:19:    load(tmp)\n"
    "docs/notes.md:3:load is documented here\n"
)


def test_search_group_groups_consecutive_same_path() -> None:
    """CP-SG-001: consecutive runs (>= 2 lines) of one path become a `[file]` group; a single
    grep line, separators and prose stay as they are."""
    assert applicability(SAMPLE).ok
    assert GROUP.compress(SAMPLE, VIEW) == (
        "Found 7 matches\n"
        "[file] src/app/core.py\n"
        "  12:def load(path):\n"
        "  40:    return load(path)\n"
        "  41:    # load again\n"
        "--\n"
        "[file] tests/test_core.py\n"
        "  7:from app.core import load\n"
        "  19:    load(tmp)\n"
        "docs/notes.md:3:load is documented here\n"
    )
    assert roundtrip(SAMPLE) is not None


def test_search_group_keeps_unparsed_lines_in_place() -> None:
    """CP-SG-002 (hazard H03): separators, headers and prose stay in their position and
    content."""
    text = (
        "header line\n"
        "a.py:1:x = 1\n"
        "a.py:2:y = 2\n"
        "--\n"
        "some prose without a path\n"
        "a.py:9:z = 3\n"
        "a.py:10:w = 4\n"
        "b.py:1:q\n"
        "trailing prose"
    )
    out = roundtrip(text)
    assert out is not None
    lines = out.split("\n")
    assert lines[0] == "header line"
    assert lines[4] == "--"
    assert lines[5] == "some prose without a path"
    assert lines[-1] == "trailing prose"
    assert "b.py:1:q" in lines


@pytest.mark.parametrize(
    "path",
    [
        "C:\\Users\\dev\\project\\main.py",
        "C:/Users/dev/project/main.py",
        "d:\\work\\file.txt",
        "\\\\server\\share\\dir\\file.cs",
        "/home/dev/project/main.py",
        "relative/dir/file.go",
    ],
)
def test_search_group_windows_paths_roundtrip(path: str) -> None:
    """CP-SG-003: POSIX, Windows drive-letter (both separators) and UNC paths are grouped and
    round-trip byte for byte."""
    text = "".join(f"{path}:{n}:match number {n}\n" for n in range(1, 7))
    out = roundtrip(text)
    assert out is not None
    assert out.startswith(f"[file] {path}\n  1:match number 1\n")


def test_search_group_escaping() -> None:
    """Lines that would be read as format lines are escaped with a leading backslash and
    restored on decode."""
    text = (
        "[file] not a header\n"
        "\\starts with a backslash\n"
        "  12:looks like a group line\n"
        "a.py:1:one\n"
        "a.py:2:two\n"
        "a.py:3:three\n"
        "a.py:4:four\n"
        "a.py:5:five\n"
        "  13:right after a group\n"
    )
    out = roundtrip(text)
    assert out is not None
    lines = out.split("\n")
    assert lines[0] == "\\[file] not a header"
    assert lines[1] == "\\\\starts with a backslash"
    assert lines[2] == "\\  12:looks like a group line"
    assert lines[-2] == "\\  13:right after a group"


@pytest.mark.parametrize("ending", ["\r\n", "\n"])
def test_search_group_crlf_roundtrip(ending: str) -> None:
    """CP-SG-004: CRLF and LF round-trip; the header takes the ending of its group's first
    line."""
    text = "".join(f"src/a.py:{n}:line {n}{ending}" for n in range(1, 7)) + "end"
    out = roundtrip(text)
    assert out is not None
    assert out.startswith(f"[file] src/a.py{ending}  1:line 1{ending}")


def test_search_group_mixed_line_endings_roundtrip() -> None:
    text = (
        "src/a.py:1:one\r\n"
        "src/a.py:2:two\n"
        "src/a.py:3:three\r\n"
        "src/b.py:4:four\n"
        "src/b.py:5:five\r\n"
        "src/b.py:6:six with a lone \r inside\n"
    )
    assert roundtrip(text) is not None


def test_search_group_min_group_lines_counts_whole_segment() -> None:
    """Review A8: `min_group_lines` counts grep lines in the whole segment, not per group."""
    five = "a.py:1:x\na.py:2:x\na.py:3:x\nb.py:4:x\nb.py:5:x\n"
    assert applicability(five).ok
    four = "a.py:1:x\na.py:2:x\nb.py:4:x\nb.py:5:x\n"
    assert applicability(four).reason == "too_few_grep_lines"
    assert applicability(four, SearchGroup(min_group_lines=4)).ok


def test_search_group_no_group_reason() -> None:
    text = "".join(f"file{n}.py:{n}:x\n" for n in range(6))  # six paths, no run of two
    result = applicability(text)
    assert not result.ok and result.reason == "no_group"


@pytest.mark.parametrize(
    "line",
    [
        "Note: see 12: below",  # a word, then a colon not followed by digits and a colon
        "a:b:12:x",  # a colon inside the path
        "  12:indented",  # no path
        "12:no path",
        # S8a SCR-003: a path has no whitespace and contains `/`, `\\` or `.`
        "time 10:30:00 something",
        "2026-10-03 09:00:01 INFO request served",
        "2026-10-03T09:00:01Z INFO request served",
        "C:\\Program Files\\app\\main.py:12:x = 1",
        "Makefile:3:all: build",
    ],
)
def test_search_group_ignores_non_grep_lines(line: str) -> None:
    text = "\n".join([line] * 6) + "\n"
    assert not applicability(text).ok


GREP_PATHS = st.sampled_from(
    ["a.py", "src/x/y.ts", "C:\\w\\z.cs", "C:/w/z.cs", "\\\\srv\\sh\\f.txt", "[file] odd.py"]
)
CONTENT = st.text(alphabet=st.characters(blacklist_characters="\n"), max_size=30)
LINE = st.one_of(
    st.tuples(GREP_PATHS, st.integers(0, 99999), CONTENT).map(lambda t: f"{t[0]}:{t[1]}:{t[2]}"),
    st.just("--"),
    st.just(""),
    CONTENT,
    CONTENT.map(lambda c: "[file] " + c),
    CONTENT.map(lambda c: "\\" + c),
    st.tuples(st.integers(0, 999), CONTENT).map(lambda t: f"  {t[0]}:{t[1]}"),
)
ENDING = st.sampled_from(["\n", "\r\n"])


@settings(max_examples=400, deadline=None)
@given(st.lists(st.tuples(LINE, ENDING), min_size=0, max_size=40), st.booleans())
def prop_search_group_decode_roundtrip(lines: list[tuple[str, str]], final_ending: bool) -> None:
    """CP-SG-004 (CC-015): `decode(compress(x)) == x` byte for byte, for any mix of grep lines,
    separators, prose and look-alike lines, with LF, CRLF and a missing final ending."""
    text = "".join(line + ending for line, ending in lines)
    if lines and not final_ending:
        text = text[: -len(lines[-1][1])]
    out = GROUP.compress(text, VIEW)
    if out is not None:
        assert GROUP.decode(out) == text


def test_search_group_ignores_timestamps() -> None:
    """S8a SCR-003 (hazard H11): log timestamps are not grep lines. Before the change,
    `2026-10-03 09:00:01 INFO …` was read as path `2026-10-03 09`, line `00`, and consecutive
    lines of one hour were grouped under a fake `[file]` header (seen in the S8a-1 smoke run)."""
    spaced = "".join(
        f"2026-10-03 09:{m:02d}:{s:02d} INFO tick {m}\n" for m in range(3) for s in range(4)
    )
    iso = "".join(f"2026-10-03T09:{m:02d}:{s:02d}Z INFO tick\n" for m in range(3) for s in range(4))
    for text in (spaced, iso):
        assert applicability(text).reason == "too_few_grep_lines"
        assert GROUP.compress(text, VIEW) is None


def test_search_group_spec() -> None:
    assert (SPEC.kind, SPEC.equivalence, SPEC.default_enabled) == ("LOSSLESS", "byte", False)
    assert SPEC.version == "2"  # S8a SCR-003 changed which lines are grouped
    assert set(SPEC.assumptions) == {"reads_grouped_search", "not_quoted_verbatim"}


def test_search_group_linear_time() -> None:
    """Correctness constraint (TOKLI_TEST_STRATEGY §8): a cheap compressor is linear.

    The best of 7 runs with the garbage collector paused measures the algorithm itself, as in
    `test_reread_linear_time` (S8f): with the best of 3 and the collector on, a busy machine
    measured 16.3x once (2026-10-07) and then 3 passes in a row."""
    block = "".join(
        f"src/module_{n % 7}/file.py:{n}:    value = compute({n})\n" for n in range(200)
    )

    def elapsed(megabytes: int) -> float:
        text = block * (megabytes * 1_000_000 // len(block))
        best = float("inf")
        gc.collect()
        gc.disable()
        try:
            for _ in range(7):
                start = time.perf_counter()
                GROUP.compress(text, VIEW)
                best = min(best, time.perf_counter() - start)
        finally:
            gc.enable()
        return best

    elapsed(1)
    ratio = elapsed(20) / max(elapsed(2), 1e-6)
    assert ratio <= 15, ratio
