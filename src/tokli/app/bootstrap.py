"""Composition root (ARCH §8, ADR 0004): builds every runtime object from one config snapshot.

Nothing here runs at import time. The HTTP layer receives the built ``Services`` and never
constructs compressors, tokenizers or sinks itself.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field

from tokli.app.setup_tokenizers import required_tokenizers
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.registry import build_registry
from tokli.compression.stages import CompressionStage, FeaturesStage, Selector
from tokli.config import EffectiveConfig
from tokli.domain.models import SegmentKind
from tokli.observability.trace import TraceBuffer
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage
from tokli.telemetry.store import TelemetryStore
from tokli.tokens import CATALOG, TokenizerSpec
from tokli.tokens.calibration import OutlierWindow
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
    selector: TokenizerSelector
    mutable_kinds: frozenset[SegmentKind]
    upstream: Upstream
    traces: TraceBuffer
    store: TelemetryStore | None
    availability: Mapping[str, str]
    enabled: Mapping[str, bool]
    version: str
    policy: str = "LOSSLESS_ONLY"  # derived from the enabled compressors (CC-002)
    calibration: OutlierWindow = field(default_factory=OutlierWindow)  # OB-011


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

    parts = _compression(config, selector)
    anthropic = settings.upstreams.anthropic
    return Services(
        config=config,
        pipeline=parts.pipeline,
        selector=selector,
        mutable_kinds=parts.mutable_kinds,
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
        availability=parts.availability,
        enabled=parts.enabled,
        version=version,
        policy=parts.policy,
    )


@dataclass(frozen=True)
class _Compression:
    pipeline: Pipeline
    mutable_kinds: frozenset[SegmentKind]
    availability: Mapping[str, str]
    enabled: Mapping[str, bool]
    policy: str


def _compression(config: EffectiveConfig, selector: Selector) -> _Compression:
    """The part of the services that a configuration change rebuilds (ADR 0009)."""
    settings = config.settings
    compression = settings.compression
    enabled = {
        compressor_id: bool(toggle["enabled"])
        for compressor_id, toggle in settings.compressors.model_dump().items()
    }
    engine = Engine(
        build_registry(
            duplicate_min_tokens=settings.pruning.duplicate_min_tokens,
            duplicate_require_same_call=settings.pruning.duplicate_require_same_call,
        ),
        EngineSettings(
            enabled=enabled,
            verbatim_tools=frozenset(compression.verbatim_tools),
            min_segment_tokens=compression.min_segment_tokens,
            min_gain_tokens=compression.min_gain_tokens,
            min_gain_ratio=compression.min_gain_ratio,
            request_budget_ms=compression.request_budget_ms,
            per_call_timeout_ms=compression.per_call_timeout_ms,
            verify_lossless=compression.verify_lossless,
            result_cache_bytes=compression.result_cache_mb * 1024 * 1024,
        ),
    )
    pipeline = Pipeline(
        [RemindersStage(), FeaturesStage(selector), CompressionStage(engine, selector)]
    )
    return _Compression(
        pipeline=pipeline,
        mutable_kinds=frozenset(SegmentKind(kind) for kind in compression.segment_kinds),
        availability=dict(engine.availability()),
        enabled=enabled,
        policy=engine.policy,
    )


def rebuild(services: Services, config: EffectiveConfig) -> Services:
    """Services for a new configuration snapshot: tokenizers, upstream client, sinks and the
    trace buffer are kept; the compression pipeline is rebuilt (ADR 0009)."""
    parts = _compression(config, services.selector)
    if services.store is not None:
        services.store.set_retention(config.settings.telemetry.retention_days)
    return dataclasses.replace(
        services,
        config=config,
        pipeline=parts.pipeline,
        mutable_kinds=parts.mutable_kinds,
        availability=parts.availability,
        enabled=parts.enabled,
        policy=parts.policy,
    )
