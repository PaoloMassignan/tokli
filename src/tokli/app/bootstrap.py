"""Composition root (ARCH §8, ADR 0004): builds every runtime object from one config snapshot.

Nothing here runs at import time. The HTTP layer receives the built ``Services`` and never
constructs compressors, tokenizers or sinks itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from tokli.app.setup_tokenizers import required_tokenizers
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.registry import REGISTRY
from tokli.compression.stages import CompressionStage, FeaturesStage, Selector
from tokli.config import EffectiveConfig
from tokli.domain.models import SegmentKind
from tokli.observability.trace import TraceBuffer
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage
from tokli.telemetry.store import TelemetryStore
from tokli.tokens import CATALOG, TokenizerSpec
from tokli.tokens.counter import (
    TokenCounter,
    TokenizerSelector,
    TokenizerUnavailableError,
    load_counter,
)
from tokli.upstream.forwarder import Upstream

TELEMETRY_DB = "tokli.db"


@dataclass(frozen=True)
class Services:
    config: EffectiveConfig
    pipeline: Pipeline
    selector: Selector
    mutable_kinds: frozenset[SegmentKind]
    upstream: Upstream
    traces: TraceBuffer
    store: TelemetryStore | None
    availability: Mapping[str, str]
    enabled: Mapping[str, bool]
    version: str


class StartupError(Exception):
    def __init__(self, cause: str, fix: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.fix = fix


def bootstrap(
    config: EffectiveConfig,
    *,
    catalog: Mapping[str, TokenizerSpec] = CATALOG,
    version: str = "unknown",
    telemetry: bool = True,
) -> Services:
    """Loads tokenizers (TM-006: fails with StartupError), builds the pipeline and the sinks."""
    settings = config.settings
    counters: dict[str, TokenCounter] = {}
    for name in required_tokenizers(settings):
        try:
            counters[name] = load_counter(catalog[name], config.dirs.data_dir)
        except TokenizerUnavailableError as exc:
            raise StartupError(cause=str(exc), fix="run 'tokli setup tokenizers'") from exc
    selector = TokenizerSelector(
        counters,
        default=settings.tokens.default,
        model_map=[(entry.pattern, entry.tokenizer) for entry in settings.tokens.model_map],
    )

    compression = settings.compression
    enabled = {
        compressor_id: bool(toggle["enabled"])
        for compressor_id, toggle in settings.compressors.model_dump().items()
    }
    engine = Engine(
        REGISTRY,
        EngineSettings(
            enabled=enabled,
            verbatim_tools=frozenset(compression.verbatim_tools),
            min_segment_tokens=compression.min_segment_tokens,
            min_gain_tokens=compression.min_gain_tokens,
            min_gain_ratio=compression.min_gain_ratio,
            request_budget_ms=compression.request_budget_ms,
            per_call_timeout_ms=compression.per_call_timeout_ms,
            verify_lossless=compression.verify_lossless,
        ),
    )
    pipeline = Pipeline(
        [RemindersStage(), FeaturesStage(selector), CompressionStage(engine, selector)]
    )

    anthropic = settings.upstreams.anthropic
    return Services(
        config=config,
        pipeline=pipeline,
        selector=selector,
        mutable_kinds=frozenset(SegmentKind(kind) for kind in compression.segment_kinds),
        upstream=Upstream(
            anthropic.base_url,
            anthropic.connect_timeout_s,
            anthropic.read_timeout_s,
            settings.tls.ca_bundle,
        ),
        traces=TraceBuffer(settings.observability.trace_buffer),
        store=(
            TelemetryStore(config.dirs.data_dir / TELEMETRY_DB, settings.telemetry.retention_days)
            if telemetry
            else None
        ),
        availability=dict(engine.availability()),
        enabled=enabled,
        version=version,
    )
