"""Compressor contract (SPEC 009). A compressor is a pure function plus metadata; the engine owns
policy, filters, the acceptance gate, invariants, timing and records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from tokli.domain.models import SegmentKind, Span
from tokli.domain.stage import Features

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


class Compressor(Protocol):
    @property
    def spec(self) -> CompressorSpec: ...

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability: ...

    def compress(self, text: str, view: SegmentView) -> str | None: ...


class LosslessCompressor(Compressor, Protocol):
    def decode(self, text: str) -> str: ...

    def equivalent(self, original: str, decoded: str) -> bool:
        """The declared equivalence (byte or structural) between an original and a decoding."""
        ...
