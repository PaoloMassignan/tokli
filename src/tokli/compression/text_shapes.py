"""Line shapes shared by the routing features (SPEC 011) and the compressors that use them
(SPEC 010): grep lines and log levels. One definition each, so a feature and its compressor
never disagree. Every pattern is a compiled regular expression without nested quantifiers, so
the work stays linear in the text and runs in C."""

from __future__ import annotations

import re
from functools import lru_cache

# A grep line `<path>:<line>:<content>`: the path is a drive-letter path (`C:\…`, `C:/…`) or a
# POSIX, relative or UNC (`\\server\share\…`) path; it holds no `:` (other than the drive
# colon) and no whitespace, and contains at least one `/`, `\` or `.`, so timestamps such as
# `2026-10-03 09:00:01` are not paths (S8a SCR-003). `<line>` is ASCII digits.
_GREP_HEAD = r"(?:[A-Za-z]:[\\/][^:\s]*|(?=[^:\s]*[./\\])[^:\s]+):([0-9]+):"
_GREP = re.compile(_GREP_HEAD)
_GREP_LINES = re.compile(r"^" + _GREP_HEAD, re.MULTILINE)

# Log levels (SPEC 010 `log_filter`): whole words, case-insensitive.
_KEYWORDS = r"FATAL|CRITICAL|ERROR|EXCEPTION|WARNING|WARN|INFO|NOTICE|DEBUG|TRACE"
_KEYWORD = re.compile(r"\b(" + _KEYWORDS + r")\b", re.IGNORECASE)
_LEVELED_LINES = re.compile(r"^[^\n]*?\b(?:" + _KEYWORDS + r")\b", re.IGNORECASE | re.MULTILINE)
_SEVERE = frozenset({"FATAL", "CRITICAL", "ERROR", "EXCEPTION", "WARNING", "WARN"})
_ROUTINE_ORDER = ("TRACE", "DEBUG", "NOTICE", "INFO")  # most verbose first
_KEYWORD_HINTS = (
    "fatal",
    "critical",
    "error",
    "exception",
    "warn",
    "info",
    "notice",
    "debug",
    "trace",
)


def split_lines(text: str) -> list[str]:
    """Lines with their endings, split on ``\\n`` only (a lone ``\\r`` stays inside a line)."""
    if not text:
        return []
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def line_count(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def every_line_crlf(text: str) -> bool:
    newlines = text.count("\n")
    return bool(text) and text.endswith("\n") and text.count("\r\n") == newlines


def parse_grep_line(line: str) -> tuple[str, str] | None:
    """``(path, rest)`` for a grep line ``<path>:<line>:<content>``, where ``rest`` is
    ``<line>:<content>`` with the line ending; ``None`` for any other line."""
    match = _GREP.match(line)
    if match is None:
        return None
    number_start = match.start(1)
    return line[: number_start - 1], line[number_start:]


def grep_line_count(text: str) -> int:
    return len(_GREP_LINES.findall(text))


def leveled_line_count(text: str) -> int:
    lowered = text.lower()
    if not any(hint in lowered for hint in _KEYWORD_HINTS):
        return 0  # cheap pre-check: no keyword substring, so no leveled line
    return len(_LEVELED_LINES.findall(text))


@lru_cache(maxsize=8192)  # as the token counter: a resent conversation repeats its texts
def shape_counts(text: str) -> tuple[int, int, int, bool]:
    """``(grep lines, leveled lines, lines, every line CRLF)`` for the routing features."""
    return grep_line_count(text), leveled_line_count(text), line_count(text), every_line_crlf(text)


def line_level(line: str) -> str | None:
    """``severe``, ``TRACE``, ``DEBUG``, ``NOTICE`` or ``INFO`` for a leveled line (a severe
    keyword wins; otherwise the most verbose routine keyword), else ``None``."""
    found = {word.upper() for word in _KEYWORD.findall(line)}
    if not found:
        return None
    if found & _SEVERE:
        return "severe"
    return next(level for level in _ROUTINE_ORDER if level in found)
