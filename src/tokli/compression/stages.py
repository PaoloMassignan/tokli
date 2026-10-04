"""The ``analyze.features`` and ``transform.compression`` stages (SPEC 007, 011)."""

from __future__ import annotations

from typing import Literal, Protocol

from tokli.compression.engine import Counter, Engine, _features
from tokli.domain.models import CanonicalRequest
from tokli.domain.stage import StageContext, StageResult, StageView


class Selector(Protocol):
    def select(self, model: str | None) -> Counter: ...


class FeaturesStage:
    """Computes ``tokens`` and ``json_candidate`` for every mutable segment (RT-001, S1 subset)."""

    id = "analyze.features"
    kind: Literal["analyzer"] = "analyzer"

    def __init__(self, selector: Selector) -> None:
        self._selector = selector

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult:
        counter = self._selector.select(request.model)
        return StageResult(
            features={
                segment.id: _features(view.texts[segment.id], counter)
                for segment in request.segments
                if segment.mutable
            }
        )


class CompressionStage:
    id = "transform.compression"
    kind: Literal["transformer"] = "transformer"

    def __init__(self, engine: Engine, selector: Selector) -> None:
        self._engine = engine
        self._selector = selector

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult:
        result = self._engine.run(
            request, view, self._selector.select(request.model), ctx.conversation
        )
        return StageResult(patches=result.patches, report=result)
