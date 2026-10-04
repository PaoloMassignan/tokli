"""SPEC 011 RT-001 features added in S8a-1: `grep_lines`, `leveled_ratio`, `line_count`, `crlf`."""

from __future__ import annotations

from tests.helpers import FakeCounter
from tokli.compression.engine import _features


def test_grep_feature_windows_paths() -> None:
    """`grep_lines` counts grep lines as `search_group` defines them: POSIX, drive-letter (both
    separators) and UNC paths; look-alike lines are not counted."""
    text = (
        "src/a.py:1:x\n"
        "C:\\w\\b.cs:22:y\n"
        "C:/w/b.cs:23:y\n"
        "\\\\srv\\share\\c.txt:3:z\n"
        "Note: not 12: grep\n"
        "  4:indented\n"
        "--\n"
    )
    assert _features(text, FakeCounter()).grep_lines == 4


def test_grep_feature_ignores_timestamps() -> None:
    """S8a SCR-003: the feature uses the same definition as the compressor."""
    text = "2026-10-03 09:00:01 INFO a\n2026-10-03T09:00:02Z INFO b\nMakefile:3:all\n"
    assert _features(text, FakeCounter()).grep_lines == 0


def test_leveled_ratio_feature() -> None:
    """`leveled_ratio`: share of lines with a level keyword (whole word, case-insensitive)."""
    text = "INFO a\nerror b\ninformation c\nplain d\n"
    assert _features(text, FakeCounter()).leveled_ratio == 0.5


def test_line_count_and_crlf_features() -> None:
    features = _features("a\r\nb\r\nc\r\n", FakeCounter())
    assert (features.line_count, features.crlf) == (3, True)
    features = _features("a\r\nb\nc", FakeCounter())
    assert (features.line_count, features.crlf) == (3, False)
    assert _features("", FakeCounter()).line_count == 0
