"""``log_filter``: keep severe and unleveled log lines, the first of each routine INFO/NOTICE
pattern and a sample of DEBUG/TRACE lines (SPEC 010, CP-LF-001…004). SELECTIVE.

A routine line's pattern is the line (without its ending) with every run of ≥ 8 hexadecimal
characters that contains a digit, then every run of digits, replaced by ``#``. An omission note
with the counts per level is appended as the last line (S8a review A6 for its line ending).
"""

from __future__ import annotations

import re
from collections import Counter

from tokli.compression.contract import Applicability, CompressorSpec, SegmentView
from tokli.compression.text_shapes import line_level, split_lines
from tokli.domain.models import SegmentKind
from tokli.domain.stage import Features

SPEC = CompressorSpec(
    id="log_filter",
    name="Log filter",
    version="1",
    kind="SELECTIVE",
    equivalence="none",
    scope="segment",
    prefix_stable=True,
    guarantees=(
        "severe and unleveled lines kept verbatim (test_log_filter_keeps_error_and_warn)",
        "unleveled lines kept verbatim (test_log_filter_keeps_unleveled_lines)",
        "line order preserved (test_log_filter_order_preserved)",
        "applicable only with >= 10 % leveled lines (test_log_filter_gate)",
        "omission note with counts per level (test_log_filter_omission_note)",
        "routine lines kept only by normalisation and sampling "
        "(test_log_filter_normalisation_and_sampling)",
        "a line with a severe keyword is severe (test_log_filter_mixed_keywords_kept_as_severe)",
    ),
    assumptions=("omitted_log_lines_not_needed", "not_quoted_verbatim"),
    stage="domain",
    segment_kinds=frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT}),
    min_tokens=0,
    cost_class="cheap",
    terminal=False,
    requires=(),
    default_enabled=False,
)

_HEX_RUN = re.compile(r"[0-9A-Fa-f]{8,}")
_DIGIT_RUN = re.compile(r"[0-9]+")
_NOTE_ORDER = ("INFO", "NOTICE", "DEBUG", "TRACE")


def _hex_to_hash(match: re.Match[str]) -> str:
    run = match.group()
    return "#" if any(c.isdigit() for c in run) else run


def _pattern(line: str) -> str:
    body = line.rstrip("\n")
    if body.endswith("\r"):
        body = body[:-1]
    return _DIGIT_RUN.sub("#", _HEX_RUN.sub(_hex_to_hash, body))


class LogFilter:
    spec = SPEC

    def __init__(self, debug_sample: int = 10) -> None:
        self._debug_sample = debug_sample

    def _filter(self, text: str) -> tuple[list[str], Counter[str], str]:
        """Kept lines, omitted counts per level, and an empty reason when something goes."""
        lines = split_lines(text)
        levels = [line_level(line) for line in lines]
        leveled = sum(1 for level in levels if level is not None)
        if not lines or leveled * 10 < len(lines):  # CP-LF-002: at least 10 % leveled
            return lines, Counter(), "too_few_leveled_lines"
        kept: list[str] = []
        omitted: Counter[str] = Counter()
        first_seen: set[str] = set()
        sampled: Counter[str] = Counter()
        for line, level in zip(lines, levels, strict=True):
            if level is None or level == "severe":
                kept.append(line)
            elif level in ("INFO", "NOTICE"):
                pattern = _pattern(line)
                if pattern in first_seen:
                    omitted[level] += 1
                else:
                    first_seen.add(pattern)
                    kept.append(line)
            else:  # DEBUG, TRACE: occurrences 1, 1+k, 1+2k, …
                pattern = _pattern(line)
                if sampled[pattern] % self._debug_sample == 0:
                    kept.append(line)
                else:
                    omitted[level] += 1
                sampled[pattern] += 1
        return kept, omitted, "" if omitted else "nothing_omitted"

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability:
        leveled = round(features.leveled_ratio * features.line_count)  # exact integer again
        if features.line_count and leveled * 10 < features.line_count:
            return Applicability(False, "too_few_leveled_lines")  # routing feature (RT-002)
        _, _, reason = self._filter(text)
        return Applicability(not reason, reason)

    def compress(self, text: str, view: SegmentView) -> str | None:
        kept, omitted, reason = self._filter(text)
        if reason:
            return None
        lines = split_lines(text)
        ending = "\r\n" if all(line.endswith("\r\n") for line in lines) else "\n"
        out = "".join(kept)
        if not out.endswith("\n"):
            out += ending
        counts = ", ".join(f"{omitted[level]} {level}" for level in _NOTE_ORDER if omitted[level])
        return f"{out}[tokli: omitted {counts} lines]{ending}"
