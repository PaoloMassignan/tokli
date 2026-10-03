"""Persisted record types (TOKLI_TELEMETRY_AND_COST §2, schema v1; ADR 0003)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequestRecord:
    request_id: str
    ts_start: str
    ts_end: str
    provider: str
    protocol: str | None
    endpoint: str
    model: str | None
    stream: bool
    auth_mode: str
    credential_kind: str
    policy: str
    config_hash: str
    outcome: str  # compressed | passthrough | verbatim_route | error
    passthrough_reason: str | None
    segments_total: int
    segments_mutable: int
    segments_changed: int
    tokenizer_id: str | None
    est_original_tokens: int | None
    est_forwarded_tokens: int | None
    status_code: int | None
    ms_parse: float | None
    ms_pipeline: float | None
    ms_render: float | None
    ms_upstream_ttfb: float | None
    ms_upstream_total: float | None
    ms_tokli_overhead: float | None
    ms_total: float | None
    error_code: str | None = None
    est_request_tokens_original: int | None = None
    est_request_tokens_forwarded: int | None = None
    usage_source: str = "unavailable"
    usage_input: int | None = None
    usage_cache_read: int | None = None
    usage_cache_write_5m: int | None = None
    usage_cache_write_1h: int | None = None
    usage_output: int | None = None
    usage_reasoning: int | None = None
    calibration_k: float | None = None
    history_rewritten: bool = False
    reference_stubs: int = 0
    header_names: tuple[str, ...] | None = None


@dataclass(frozen=True)
class CompressorStatsRecord:
    request_id: str
    compressor_id: str
    compressor_version: str
    kind: str
    considered: int
    applicable: int
    accepted: int
    rejected_no_gain: int
    rejected_invariant: int
    failed: int
    skipped_budget: int
    tokens_in: int
    tokens_out: int
    marginal_saved: int
    ms_total: float
    skip_reasons: dict[str, int] = field(default_factory=dict)
