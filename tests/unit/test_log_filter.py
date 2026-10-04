"""SPEC 010 `log_filter` (S8a-1): CP-LF-001…004, review A6, reason codes, linear time."""

from __future__ import annotations

import time

import pytest

from tests.helpers import FakeCounter
from tokli.compression.contract import SegmentView
from tokli.compression.engine import _features
from tokli.compressors.log_filter import SPEC, LogFilter
from tokli.domain.models import SegmentKind

VIEW = SegmentView(SegmentKind.TOOL_RESULT, "user", "ci_logs", False, ())
FILTER = LogFilter()


def applicability(text: str, compressor: LogFilter = FILTER):  # type: ignore[no-untyped-def]
    return compressor.applicable(text, VIEW, _features(text, FakeCounter()))


def filtered(text: str, compressor: LogFilter = FILTER) -> str:
    assert applicability(text, compressor).ok, applicability(text, compressor)
    out = compressor.compress(text, VIEW)
    assert out is not None
    return out


def info_lines(n: int) -> str:
    return "".join(
        f"2026-10-03 12:00:{i:02d} INFO request {1000 + i} served in {i} ms\n" for i in range(n)
    )


def test_log_filter_keeps_error_and_warn() -> None:
    """CP-LF-001: every severe line is kept verbatim."""
    text = (
        info_lines(5)
        + "2026-10-03 12:01:00 ERROR request 77 failed: code E42\n"
        + info_lines(5)
        + "2026-10-03 12:02:00 WARNING disk 91 % full\n"
        + "2026-10-03 12:03:00 FATAL out of memory\n"
        + "Traceback CRITICAL section\n"
    )
    out = filtered(text)
    for line in (
        "2026-10-03 12:01:00 ERROR request 77 failed: code E42\n",
        "2026-10-03 12:02:00 WARNING disk 91 % full\n",
        "2026-10-03 12:03:00 FATAL out of memory\n",
        "Traceback CRITICAL section\n",
    ):
        assert line in out


def test_log_filter_keeps_unleveled_lines() -> None:
    """CP-LF-001: lines without a level keyword are kept verbatim (stack traces, prose)."""
    text = info_lines(8) + '  File "app.py", line 3, in main\n    raise ValueError(x)\n'
    out = filtered(text)
    assert '  File "app.py", line 3, in main\n    raise ValueError(x)\n' in out


def test_log_filter_order_preserved() -> None:
    """CP-LF-001: kept lines keep their relative order."""
    text = (
        "start\n"
        + info_lines(6)
        + "ERROR one\n"
        + info_lines(6)
        + "middle\n"
        + "ERROR two\n"
        + info_lines(6)
        + "end\n"
    )
    out = filtered(text)
    kept = [line for line in out.split("\n") if line and not line.startswith("[tokli:")]
    original = text.split("\n")
    positions = [original.index(line) for line in kept]
    assert positions == sorted(positions)
    assert kept[0] == "start" and kept[-1] == "end"


def test_log_filter_gate() -> None:
    """CP-LF-002: fewer than 10 % leveled lines → not applicable."""
    prose = "".join(f"plain line {i}\n" for i in range(91))
    nine = prose + "".join(f"INFO a {i}\n" for i in range(1, 10))
    result = applicability(nine)  # 9 of 100 lines leveled
    assert not result.ok and result.reason == "too_few_leveled_lines"
    ten = prose[: -len("plain line 90\n")] + "INFO a 1\n" * 10  # 10 of 100 lines leveled
    assert applicability(ten).ok


def test_log_filter_omission_note() -> None:
    """CP-LF-003: a note with only non-zero counts per level, in the fixed order."""
    text = (
        "".join(f"INFO tick {i}\n" for i in range(5))
        + "".join(f"DEBUG poll {i}\n" for i in range(12))
        + "ERROR boom\n"
    )
    out = filtered(text)
    assert out.endswith("[tokli: omitted 4 INFO, 10 DEBUG lines]\n")


def test_log_filter_note_line_endings() -> None:
    """Review A6: CRLF note when every line ends with CRLF; a missing final ending is added
    before the note."""
    crlf = "".join(f"INFO tick {i}\r\n" for i in range(5)) + "ERROR boom\r\n"
    assert filtered(crlf).endswith("ERROR boom\r\n[tokli: omitted 4 INFO lines]\r\n")
    no_final = "".join(f"INFO tick {i}\n" for i in range(5)) + "ERROR boom"
    assert filtered(no_final).endswith("ERROR boom\n[tokli: omitted 4 INFO lines]\n")
    mixed = "INFO tick 1\r\n" + "".join(f"INFO tick {i}\n" for i in range(5)) + "ERROR boom\n"
    assert filtered(mixed).endswith("[tokli: omitted 5 INFO lines]\n")


def test_log_filter_normalisation_and_sampling() -> None:
    """CP-LF-004: INFO/NOTICE keep the first line per normalised pattern (digit runs and
    hex runs of >= 8 with a digit become `#`); DEBUG/TRACE keep occurrences 1, 1+k, 1+2k…"""
    text = (
        "INFO user 17 logged in from 10.0.0.1\n"
        "INFO user 18 logged in from 10.0.0.2\n"
        "NOTICE commit deadbeef12 pushed\n"
        "NOTICE commit cafebabe34 pushed\n"
        "NOTICE commit abcdefgh pushed\n"  # 'abcdefgh' is not hex: a different pattern
        + "".join(f"DEBUG poll {i}\n" for i in range(25))
        + "ERROR done\n"
    )
    out = filtered(text)
    assert "INFO user 17 logged in from 10.0.0.1\n" in out
    assert "INFO user 18" not in out
    assert "NOTICE commit deadbeef12 pushed\n" in out
    assert "cafebabe34" not in out
    assert "NOTICE commit abcdefgh pushed\n" in out
    kept_debug = [line for line in out.split("\n") if line.startswith("DEBUG")]
    assert kept_debug == ["DEBUG poll 0", "DEBUG poll 10", "DEBUG poll 20"]
    three = [
        line
        for line in filtered(text, LogFilter(debug_sample=3)).split("\n")
        if line.startswith("DEBUG")
    ]
    assert three == [f"DEBUG poll {i}" for i in range(0, 25, 3)]


def test_log_filter_mixed_keywords_kept_as_severe() -> None:
    """A line with any severe keyword is severe, even with a routine keyword."""
    text = "".join(f"INFO tick {i}\n" for i in range(6)) + "INFO handler raised ERROR 5\n" * 3
    out = filtered(text)
    assert out.count("INFO handler raised ERROR 5\n") == 3


def test_log_filter_most_verbose_routine_level_wins() -> None:
    """A line with only routine keywords takes the most verbose one (TRACE > DEBUG > NOTICE >
    INFO): `INFO … DEBUG` is sampled as DEBUG."""
    text = "".join(f"INFO step DEBUG detail {i}\n" for i in range(12)) + "ERROR x\n"
    out = filtered(text)
    assert out.endswith("[tokli: omitted 10 DEBUG lines]\n")


@pytest.mark.parametrize("word", ["information", "infos", "Debugger", "errors", "warned"])
def test_log_filter_keywords_are_whole_words(word: str) -> None:
    text = "".join(f"{word} line {i}\n" for i in range(20))
    assert applicability(text).reason == "too_few_leveled_lines"


def test_log_filter_keywords_case_insensitive() -> None:
    text = "".join(f"info tick {i}\n" for i in range(5)) + "Error boom\n"
    assert filtered(text).endswith("Error boom\n[tokli: omitted 4 INFO lines]\n")


def test_log_filter_nothing_omitted_reason() -> None:
    text = "ERROR a\nWARN b\nINFO only once 1\nplain\n"
    result = applicability(text)
    assert not result.ok and result.reason == "nothing_omitted"


def test_log_filter_spec() -> None:
    assert (SPEC.kind, SPEC.equivalence, SPEC.default_enabled) == ("SELECTIVE", "none", False)
    assert set(SPEC.assumptions) == {"omitted_log_lines_not_needed", "not_quoted_verbatim"}


def test_log_filter_linear_time() -> None:
    """Correctness constraint (TOKLI_TEST_STRATEGY §8): a cheap compressor is linear."""
    block = "".join(
        f"2026-10-03 12:00:{n % 60:02d} {'DEBUG' if n % 3 else 'INFO'} "
        f"worker {n % 5} handled job {n}\n"
        for n in range(300)
    )

    def elapsed(megabytes: int) -> float:
        text = block * (megabytes * 1_000_000 // len(block))
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            FILTER.compress(text, VIEW)
            best = min(best, time.perf_counter() - start)
        return best

    elapsed(1)
    ratio = elapsed(20) / max(elapsed(2), 1e-6)
    assert ratio <= 15, ratio
