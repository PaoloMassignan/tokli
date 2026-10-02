"""Runs a fixed list of stages (decision C2) with per-stage timing and isolation (PL-003…PL-006).

Analyzers run before transformers in the fixed list, so protected spans always refer to the
original segment texts.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from tokli.domain.models import CanonicalRequest, Patch, Span
from tokli.domain.spans import spans_preserved
from tokli.domain.stage import Features, Stage, StageContext, StageResult, StageView


@dataclass(frozen=True)
class StageOutcome:
    stage_id: str
    ms: float
    status: str  # "ok" | "error"
    reason: str = ""


@dataclass(frozen=True)
class PipelineResult:
    patches: tuple[Patch, ...]
    texts: Mapping[str, str]
    spans: Mapping[str, Sequence[Span]]
    features: Mapping[str, Features]
    reports: Mapping[str, object]
    outcomes: tuple[StageOutcome, ...]


class Pipeline:
    def __init__(
        self,
        stages: Sequence[Stage],
        stage_budget_ms: float = 1000.0,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._stages = tuple(stages)
        self._budget_ms = stage_budget_ms
        self._clock = clock

    @property
    def stage_ids(self) -> tuple[str, ...]:
        return tuple(stage.id for stage in self._stages)

    def run(self, request: CanonicalRequest, ctx: StageContext) -> PipelineResult:
        texts = {segment.id: segment.text for segment in request.segments}
        spans: dict[str, list[Span]] = {}
        features: dict[str, Features] = {}
        producers: dict[str, tuple[str, ...]] = {}
        reports: dict[str, object] = {}
        outcomes: list[StageOutcome] = []

        for stage in self._stages:
            view = StageView(
                texts=MappingProxyType(dict(texts)),
                spans=MappingProxyType({k: tuple(v) for k, v in spans.items()}),
                features=MappingProxyType(dict(features)),
            )
            started = self._clock()
            try:
                result = stage.run(request, view, ctx)
            except Exception:  # isolation (PL-005): the stage's result is discarded
                ms = (self._clock() - started) * 1000
                outcomes.append(StageOutcome(stage.id, ms, "error", f"stage_exception({stage.id})"))
                continue
            ms = (self._clock() - started) * 1000
            if ms > self._budget_ms:
                outcomes.append(StageOutcome(stage.id, ms, "error", f"stage_timeout({stage.id})"))
                continue

            if stage.kind == "analyzer":
                if result.patches:
                    outcomes.append(
                        StageOutcome(stage.id, ms, "error", "analyzer_returned_patches")
                    )
                    continue
                for segment_id, found in result.protected_spans.items():
                    spans.setdefault(segment_id, []).extend(found)
                features.update(result.features)
                reports[stage.id] = result.report
                outcomes.append(StageOutcome(stage.id, ms, "ok"))
                continue

            dropped = self._apply(request, result, spans, texts, producers)
            reports[stage.id] = result.report
            outcomes.append(
                StageOutcome(stage.id, ms, "ok", "protected_span_changed" if dropped else "")
            )

        patches = tuple(
            Patch(segment.id, texts[segment.id], producers[segment.id])
            for segment in request.segments
            if texts[segment.id] != segment.text
        )
        return PipelineResult(
            patches=patches,
            texts=MappingProxyType(texts),
            spans=MappingProxyType({k: tuple(v) for k, v in spans.items()}),
            features=MappingProxyType(features),
            reports=MappingProxyType(reports),
            outcomes=tuple(outcomes),
        )

    @staticmethod
    def _apply(
        request: CanonicalRequest,
        result: StageResult,
        spans: Mapping[str, Sequence[Span]],
        texts: dict[str, str],
        producers: dict[str, tuple[str, ...]],
    ) -> bool:
        """Applies a transformer's patches and drops the disallowed ones. True if any dropped."""
        dropped = False
        for patch in result.patches:
            segment = request.segment(patch.segment_id)
            if not segment.mutable or not spans_preserved(
                segment.text, spans.get(segment.id, ()), patch.new_text
            ):
                dropped = True
                continue
            texts[segment.id] = patch.new_text
            producers[segment.id] = producers.get(segment.id, ()) + patch.produced_by
        return dropped
