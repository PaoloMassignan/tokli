"""Composition root (ARCH §8, ADR 0004): builds every runtime object from one config snapshot.

Nothing here runs at import time. The HTTP layer receives the built ``Services`` and never
constructs compressors, tokenizers or sinks itself.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from tokli.app.conversations import ConversationStore
from tokli.app.setup_tokenizers import required_tokenizers
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.registry import build_registry
from tokli.compression.stages import CompressionStage, FeaturesStage, Selector
from tokli.config import EffectiveConfig
from tokli.domain.models import SegmentKind
from tokli.observability.trace import TraceBuffer
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage
from tokli.pricing.book import PriceBookError, PriceTable, load_shipped, load_user
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
    # Conversation state for `edit_args_on_resume` (ADR 0012); kept across config changes.
    conversations: ConversationStore = field(default_factory=ConversationStore)
    # Argument strings exposed as TOOL_CALL_ARGS, only while `edit_args_on_resume` is on.
    arg_fields: Mapping[str, Sequence[str]] = field(default_factory=dict)
    prices: PriceTable = field(default_factory=lambda: PriceTable(load_shipped()))


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

    try:
        prices = PriceTable(load_shipped(), load_user(config.dirs.data_dir))  # TC-018
    except PriceBookError as exc:
        raise StartupError(
            cause=f"invalid price book: {exc}",
            fix="correct the file, or remove it to use the shipped prices",
        ) from exc

    parts = _compression(config, selector)
    anthropic = settings.upstreams.anthropic
    return Services(
        config=config,
        pipeline=parts.pipeline,
        selector=selector,
        mutable_kinds=parts.mutable_kinds,
        arg_fields=parts.arg_fields,
        upstream=Upstream(
            anthropic.base_url,
            anthropic.connect_timeout_s,
            anthropic.read_timeout_s,
            settings.tls.ca_bundle,
        ),
        traces=TraceBuffer(settings.observability.trace_buffer),
        prices=prices,
        store=(
            TelemetryStore(config.dirs.data_dir / TELEMETRY_DB, settings.telemetry.retention_days)
            if telemetry
            else None
        ),
        availability=parts.availability,
        enabled=parts.enabled,
        version=version,
        policy=parts.policy,
        conversations=ConversationStore(settings.pruning.conversation_states),
    )


@dataclass(frozen=True)
class _Compression:
    pipeline: Pipeline
    mutable_kinds: frozenset[SegmentKind]
    availability: Mapping[str, str]
    enabled: Mapping[str, bool]
    policy: str
    arg_fields: Mapping[str, Sequence[str]]


def _compression(config: EffectiveConfig, selector: Selector) -> _Compression:
    """The part of the services that a configuration change rebuilds (ADR 0009)."""
    settings = config.settings
    compression = settings.compression
    options = settings.compressors.model_dump()
    enabled = {compressor_id: bool(toggle["enabled"]) for compressor_id, toggle in options.items()}
    resume_on = enabled.get("edit_args_on_resume", False)  # SPEC 019 PR-020
    opted_in = frozenset(  # CC-021 (b), S8a SCR-001
        compressor_id
        for compressor_id, toggle in options.items()
        if toggle.get("apply_to_verbatim_tools")
    )
    engine = Engine(
        build_registry(
            duplicate_min_tokens=settings.pruning.duplicate_min_tokens,
            duplicate_require_same_call=settings.pruning.duplicate_require_same_call,
            search_group_min_lines=settings.compressors.search_group.min_group_lines,
            log_debug_sample=settings.compressors.log_filter.debug_sample,
            resume_after_s=settings.pruning.resume_after_s,
            resume_min_age_turns=settings.pruning.resume_min_age_turns,
            resume_min_tokens=settings.pruning.resume_min_tokens,
            reread_tools=tuple(settings.pruning.reread_tools),
            reread_min_run_lines=settings.pruning.reread_min_run_lines,
            reread_max_lines=settings.pruning.reread_max_lines,
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
            verbatim_opt_in=opted_in,
        ),
    )
    pipeline = Pipeline(
        [RemindersStage(), FeaturesStage(selector), CompressionStage(engine, selector)]
    )
    return _Compression(
        pipeline=pipeline,
        mutable_kinds=frozenset(SegmentKind(kind) for kind in compression.segment_kinds)
        | ({SegmentKind.TOOL_CALL_ARGS} if resume_on else set()),
        arg_fields=dict(settings.pruning.resume_edit_fields) if resume_on else {},
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
        arg_fields=parts.arg_fields,
        availability=parts.availability,
        enabled=parts.enabled,
        policy=parts.policy,
    )
