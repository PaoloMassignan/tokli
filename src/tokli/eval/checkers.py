"""Deterministic checkers (QE-004, QE-020). None of them normalises away content that a
compressor could remove: values are compared exactly, JSON structurally."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

_STRIP = "`\"'"


def exact_value(answer: str, expected: str) -> bool:
    """The answer's last non-empty line equals the expected value, after trimming whitespace
    and surrounding quotes or backticks."""
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if not lines:
        return False
    return lines[-1].strip(_STRIP).strip() == expected.strip()


def _first_json(text: str) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "{[":
            try:
                value, _ = decoder.raw_decode(text, index)
            except ValueError:
                continue
            return value
    raise ValueError("no JSON value")


def json_structural(answer: str, expected: str) -> bool:
    """The first JSON value in the answer equals the expected JSON (key order and whitespace
    ignored; list order and types count)."""
    try:
        return bool(_first_json(answer) == json.loads(expected))
    except ValueError:
        return False


def verbatim_line(answer: str, expected: str) -> bool:
    """The answer's last non-empty line equals the expected line byte for byte, leading
    whitespace included (an edit anchor). Code-fence lines are not lines of the answer, and
    surrounding quotes or backticks are removed; a trailing CR is a line ending, not content."""
    for line in reversed(answer.split("\n")):
        line = line.removesuffix("\r")
        if not line.strip() or line.strip().startswith("```"):
            continue
        if len(line) >= 2 and line[0] == line[-1] and line[0] in _STRIP:
            line = line[1:-1]
        return line == expected
    return False


CHECKERS: dict[str, Callable[[str, str], bool]] = {
    "exact_value": exact_value,
    "json_structural": json_structural,
    "verbatim_line": verbatim_line,
}
