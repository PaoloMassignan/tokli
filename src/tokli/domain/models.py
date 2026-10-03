"""Canonical request model (SPEC 001): the text values a stage may read or replace."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class SegmentKind(enum.StrEnum):
    SYSTEM = "SYSTEM"
    TOOL_DESCRIPTION = "TOOL_DESCRIPTION"
    USER_TEXT = "USER_TEXT"
    ASSISTANT_TEXT = "ASSISTANT_TEXT"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_RESULT = "TOOL_RESULT"
    OTHER_TEXT = "OTHER_TEXT"


# Kinds that may ever be mutable in v1 (CM-009); config narrows this further.
MUTABLE_ELIGIBLE: frozenset[SegmentKind] = frozenset(
    {SegmentKind.USER_TEXT, SegmentKind.TOOL_RESULT}
)


@dataclass(frozen=True)
class Span:
    """``[start, end)`` character offsets into a segment's text."""

    start: int
    end: int
    reason: str


@dataclass(frozen=True)
class Segment:
    id: str
    index: int
    kind: SegmentKind
    role: str | None
    text: str
    locator: str  # RFC 6901 JSON Pointer into the original body
    mutable: bool
    tool_name: str | None = None
    tool_call_id: str | None = None
    is_error: bool = False
    cache_breakpoint_after: bool = False
    whole_result: bool = False  # the segment is the entire content of its tool result


@dataclass(frozen=True)
class Patch:
    segment_id: str
    new_text: str
    produced_by: tuple[str, ...]


@dataclass(frozen=True)
class ToolRecord:
    """One tool call of the request and its result segments, read-only (CM-013)."""

    call_id: str
    name: str
    arguments: Any  # parsed JSON, or the raw string
    index: int
    result_segment_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalRequest:
    protocol: str
    provider: str
    endpoint: str
    model: str | None
    stream: bool
    segments: tuple[Segment, ...]
    original_json: Any = field(repr=False)
    original_bytes: bytes = field(repr=False)
    tools: tuple[ToolRecord, ...] = ()

    def segment(self, segment_id: str) -> Segment:
        for segment in self.segments:
            if segment.id == segment_id:
                return segment
        raise KeyError(segment_id)
