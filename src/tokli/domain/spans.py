"""Protected-span preservation check (CC-007, PL-003)."""

from __future__ import annotations

from collections.abc import Sequence

from tokli.domain.models import Span


def spans_preserved(original: str, spans: Sequence[Span], new_text: str) -> bool:
    """True when every protected span's text occurs unchanged, and in order, in ``new_text``.

    Spans are matched left to right without overlap, so two spans cannot be satisfied by the
    same characters.
    """
    position = 0
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        fragment = original[span.start : span.end]
        found = new_text.find(fragment, position)
        if found < 0:
            return False
        position = found + len(fragment)
    return True
