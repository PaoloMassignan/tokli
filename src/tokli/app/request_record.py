"""Completing one request (TC-001, TC-014, OB-002; S4.5 R4).

The HTTP layer observes a request: timings, outcome, usage. This use case turns those
observations into the persisted record, the per-compressor rows, the trace view and the
structured log line.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from tokli.app.api import request_view, stats_records
from tokli.app.bootstrap import Services
from tokli.app.measurement import Calibration, RequestEstimate
from tokli.app.regions import split_for
from tokli.compression.engine import EngineResult
from tokli.domain.usage import Usage
from tokli.observability.logs import REQUEST_LOGGER, log_fields
from tokli.telemetry.records import RequestRecord

_LOG = logging.getLogger(REQUEST_LOGGER)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Observed:
    """What the proxy observed about one request, timings already closed."""

    request_id: str
    ts_start: str
    provider: str
    protocol: str | None
    endpoint: str
    model: str | None
    stream: bool
    auth_mode: str
    credential_kind: str
    outcome: str
    reason: str | None
    segments_total: int
    segments_mutable: int
    segments_changed: int
    tokenizer_id: str | None
    status_code: int | None
    ms_parse: float | None
    ms_pipeline: float | None
    ms_render: float | None
    ms_upstream_ttfb: float | None
    ms_upstream_total: float
    ms_total: float
    error_code: str | None
    header_names: tuple[str, ...]
    usage: Usage
    error_details: Mapping[str, str] = field(default_factory=dict)
    history_rewritten: bool = False  # PR-009, PR-025


def record_request(
    services: Services,
    observed: Observed,
    engine: EngineResult | None,
    estimate: RequestEstimate | None,
    calibration: Calibration,
    trace: Mapping[str, Any],
) -> RequestRecord:
    """Stores the record and its per-compressor rows, keeps the trace view and logs one line."""
    usage = observed.usage
    split = (
        split_for(engine.invocations, estimate.places, usage, calibration.k)
        if engine is not None and estimate is not None
        else None
    )
    request_parts = split.request if split is not None else (None, None, None)
    record = RequestRecord(
        request_id=observed.request_id,
        ts_start=observed.ts_start,
        ts_end=now_iso(),
        provider=observed.provider,
        protocol=observed.protocol,
        endpoint=observed.endpoint,
        model=observed.model,
        stream=observed.stream,
        auth_mode=observed.auth_mode,
        credential_kind=observed.credential_kind,
        policy=services.policy,
        config_hash=services.config.config_hash,
        outcome=observed.outcome,
        passthrough_reason=observed.reason,
        segments_total=observed.segments_total,
        segments_mutable=observed.segments_mutable,
        segments_changed=observed.segments_changed,
        tokenizer_id=observed.tokenizer_id,
        est_original_tokens=engine.est_original_tokens if engine else None,
        est_forwarded_tokens=engine.est_forwarded_tokens if engine else None,
        status_code=observed.status_code,
        ms_parse=observed.ms_parse,
        ms_pipeline=observed.ms_pipeline,
        ms_render=observed.ms_render,
        ms_upstream_ttfb=observed.ms_upstream_ttfb,
        ms_upstream_total=observed.ms_upstream_total,
        ms_tokli_overhead=max(0.0, observed.ms_total - observed.ms_upstream_total),
        ms_total=observed.ms_total,
        error_code=observed.error_code,
        est_request_tokens_original=estimate.original if estimate else None,
        est_request_tokens_forwarded=estimate.forwarded if estimate else None,
        usage_source=usage.source,
        usage_input=usage.input,
        usage_cache_read=usage.cache_read,
        usage_cache_write_5m=usage.cache_write_5m,
        usage_cache_write_1h=usage.cache_write_1h,
        usage_output=usage.output,
        calibration_k=calibration.k,
        header_names=observed.header_names,
        history_rewritten=observed.history_rewritten,
        reference_stubs=engine.reference_stubs if engine else 0,
        saved_cache_read=request_parts[0],
        saved_cache_write=request_parts[1],
        saved_input=request_parts[2],
    )
    stats = stats_records(
        observed.request_id,
        engine.stats if engine else (),
        split.per_compressor if split is not None else None,
    )
    if services.store is not None:
        services.store.submit(record, stats)
    services.traces.add(observed.request_id, request_view(record, stats, dict(trace)))
    log_fields(
        _LOG,
        logging.INFO,
        "request",
        event="request",
        request_id=observed.request_id,
        provider=observed.provider,
        model=observed.model,
        stream=observed.stream,
        outcome=observed.outcome,
        reason=observed.reason,
        status=observed.status_code,
        credential_kind=observed.credential_kind,
        overhead_ms=round(record.ms_tokli_overhead or 0.0, 3),
        tokens={
            "original": {"value": record.est_original_tokens, "method": "estimate"},
            "forwarded": {"value": record.est_forwarded_tokens, "method": "estimate"},
            "saved": (
                {"value": calibration.saving, "method": calibration.method}
                if calibration.saving is not None
                else {"value": None, "reason": "not_measured"}
            ),
            "usage": (
                {"source": usage.source, "method": "exact", **usage_categories(usage)}
                if usage.source != "unavailable"
                else {"value": None, "reason": usage.reason or "usage_unavailable"}
            ),
            "k": calibration.k,
        },
        **({"upstream_error": dict(observed.error_details)} if observed.error_details else {}),
        **(
            {
                "sse": {
                    "events": dict(usage.events),
                    "delta_usage_fields": list(usage.delta_fields),
                }
            }
            if usage.events
            else {}
        ),
    )
    return record


def usage_categories(usage: Usage) -> dict[str, int | None]:
    return {
        "input": usage.input,
        "cache_read": usage.cache_read,
        "cache_write_5m": usage.cache_write_5m,
        "cache_write_1h": usage.cache_write_1h,
        "output": usage.output,
    }
