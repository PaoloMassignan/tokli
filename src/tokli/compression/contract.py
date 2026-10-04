"""Compressor contract (SPEC 009). A compressor is a pure function plus metadata; the engine owns
policy, filters, the acceptance gate, invariants, timing and records."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from tokli.domain.models import SegmentKind, Span
from tokli.domain.stage import ConversationView, Features

Kind = Literal["LOSSLESS", "SELECTIVE", "LOSSY", "UNKNOWN"]
Equivalence = Literal["byte", "structural", "reference", "none"]


@dataclass(frozen=True)
class CompressorSpec:
    id: str
    name: str
    version: str
    kind: Kind
    equivalence: Equivalence
    scope: Literal["segment", "request"]
    prefix_stable: bool
    guarantees: tuple[str, ...]
    assumptions: tuple[str, ...]
    stage: Literal["normalize", "structural", "domain", "semantic"]
    segment_kinds: frozenset[SegmentKind]
    min_tokens: int
    cost_class: Literal["cheap", "moderate", "expensive"]
    terminal: bool
    requires: tuple[str, ...]
    default_enabled: bool


@dataclass(frozen=True)
class SegmentView:
    """What a compressor may know about a segment: no protocol or provider fields."""

    kind: SegmentKind
    role: str | None
    tool_name: str | None
    is_error: bool
    protected: Sequence[Span]


@dataclass(frozen=True)
class Applicability:
    ok: bool
    reason: str = ""


@runtime_checkable
class Compressor(Protocol):
    @property
    def spec(self) -> CompressorSpec: ...

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability: ...

    def compress(self, text: str, view: SegmentView) -> str | None: ...


@runtime_checkable
class LosslessCompressor(Compressor, Protocol):
    def decode(self, text: str) -> str: ...

    def equivalent(self, original: str, decoded: str) -> bool:
        """The declared equivalence (byte or structural) between an original and a decoding."""
        ...


@dataclass(frozen=True)
class SegmentRef:
    """A mutable segment as a request-scope compressor sees it (ADR 0010): no protocol fields."""

    segment_id: str
    view: SegmentView
    call_id: str | None
    whole_result: bool


@dataclass(frozen=True)
class ToolRecordView:
    """A tool call, read-only (CM-013): name and parsed arguments."""

    call_id: str
    name: str
    arguments: Any
    human_turns_after: int = 0  # SPEC 019 PR-026


@dataclass(frozen=True)
class Proposal:
    """A request-scope compressor's replacement for one segment; ``target_id`` names the segment
    a reference stub points to (CC-019). ``new_text=None`` leaves the segment alone and ``reason``
    says why, as a short compressor-specific code (metadata only)."""

    segment_id: str
    new_text: str | None
    target_id: str | None = None
    reason: str = ""


@runtime_checkable
class RequestCompressor(Protocol):
    """Request scope (SPEC 009, SPEC 019): sees all candidate segments and the tool records,
    returns proposals that the engine gates one by one (PR-001)."""

    @property
    def spec(self) -> CompressorSpec: ...

    def plan(
        self,
        refs: Sequence[SegmentRef],
        texts: Mapping[str, str],
        tools: Sequence[ToolRecordView],
        count: Callable[[str], int],
        conversation: ConversationView | None,
    ) -> list[Proposal]: ...

    def decode_request(
        self, texts: Mapping[str, str], refs: Sequence[SegmentRef]
    ) -> dict[str, str]: ...


# Any registered compressor: segment scope or request scope (ADR 0010).
AnyCompressor = Compressor | RequestCompressor
