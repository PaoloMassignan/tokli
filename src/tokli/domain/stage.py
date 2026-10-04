"""Stage contract (SPEC 007): analyzers mark spans and features, transformers return patches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from tokli.domain.models import CanonicalRequest, Patch, Span


@dataclass(frozen=True)
class Features:
    """Cheap per-segment features (SPEC 011), computed once by ``analyze.features``."""

    tokens: int
    json_candidate: bool
    grep_lines: int = 0  # S8a-1: grep lines as defined for search_group
    leveled_ratio: float = 0.0  # S8a-1: share of lines with a log level keyword
    line_count: int = 0
    crlf: bool = False  # every line ends with CR LF


@dataclass(frozen=True)
class StageView:
    """Read-only view of the working state: current texts, protected spans and features."""

    texts: Mapping[str, str]
    spans: Mapping[str, Sequence[Span]]
    features: Mapping[str, Features]


@dataclass(frozen=True)
class StageContext:
    request_id: str


@dataclass(frozen=True)
class StageResult:
    protected_spans: Mapping[str, Sequence[Span]] = field(default_factory=dict)
    features: Mapping[str, Features] = field(default_factory=dict)
    patches: Sequence[Patch] = ()
    report: object = None


class Stage(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def kind(self) -> Literal["analyzer", "transformer"]: ...

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult: ...
