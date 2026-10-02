"""``analyze.reminders``: protect ``<system-reminder>…</system-reminder>`` spans (SPEC 007).

A span runs from an opening tag to the nearest following closing tag (non-greedy), may cross line
breaks and includes both tags. An opening tag with no later closing tag produces no span. Tags are
matched literally and case-sensitively; nested opening tags are not interpreted.
"""

from __future__ import annotations

import re
from typing import Literal

from tokli.domain.models import CanonicalRequest, SegmentKind, Span
from tokli.domain.stage import StageContext, StageResult, StageView

_TAG = "system-reminder"
_PATTERN = re.compile(re.escape(f"<{_TAG}>") + ".*?" + re.escape(f"</{_TAG}>"), re.DOTALL)
_KINDS = frozenset({SegmentKind.USER_TEXT, SegmentKind.TOOL_RESULT})


class RemindersStage:
    id = "analyze.reminders"
    kind: Literal["analyzer"] = "analyzer"

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult:
        spans: dict[str, list[Span]] = {}
        for segment in request.segments:
            if segment.kind not in _KINDS:
                continue
            found = [
                Span(m.start(), m.end(), _TAG) for m in _PATTERN.finditer(view.texts[segment.id])
            ]
            if found:
                spans[segment.id] = found
        return StageResult(protected_spans=spans)
