"""Application-API views (SPEC 015, API-001, API-002, API-004). Metadata only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from tokli.app.evaluations import evaluation_status, records_dir
from tokli.compression.engine import CompressorStats, EngineResult
from tokli.compression.registry import REGISTRY
from tokli.config import EffectiveConfig
from tokli.telemetry.records import CompressorStatsRecord, RequestRecord
from tokli.tokens.calibration import calibrated_value

API_VERSION = 1

__all__ = [
    "API_VERSION",
    "compression_report",
    "compressor_summary",
    "compressors_view",
    "record_view",
    "request_view",
    "stats_records",
]
_ESTIMATES = (
    "est_original_tokens",
    "est_forwarded_tokens",
    "est_request_tokens_original",
    "est_request_tokens_forwarded",
)
_USAGE = (
    "usage_input",
    "usage_cache_read",
    "usage_cache_write_5m",
    "usage_cache_write_1h",
    "usage_output",
    "usage_reasoning",
)


def stats_records(request_id: str, stats: Sequence[CompressorStats]) -> list[CompressorStatsRecord]:
    """Rows for compressors considered at least once (TC-002)."""
    return [
        CompressorStatsRecord(
            request_id=request_id,
            compressor_id=s.compressor_id,
            compressor_version=s.compressor_version,
            kind=s.kind,
            considered=s.considered,
            applicable=s.applicable,
            accepted=s.accepted,
            rejected_no_gain=s.rejected_no_gain,
            rejected_invariant=s.rejected_invariant,
            failed=s.failed,
            skipped_budget=s.skipped_budget,
            tokens_in=s.tokens_in,
            tokens_out=s.tokens_out,
            marginal_saved=s.marginal_saved,
            ms_total=s.ms_total,
            skip_reasons=dict(s.skip_reasons),
            tokens_in_accepted=s.tokens_in_accepted,
        )
        for s in stats
        if s.considered > 0
    ]


def record_view(record: Mapping[str, Any]) -> dict[str, Any]:
    """Every token figure as ``{value, method}``, or ``{value: null, reason}`` when unknown
    (TM-005). Derived figures: the request ``saving`` and ``request_tokens_original``, calibrated
    when an in-range ``k`` exists."""
    view = dict(record)
    for key in _ESTIMATES:
        value = view.get(key)
        view[key] = (
            {"value": value, "method": "estimate"}
            if value is not None
            else {"value": None, "reason": "not_measured"}
        )
    source = view.get("usage_source") or "unavailable"
    for key in _USAGE:
        value = view.get(key)
        if value is None:
            view[key] = {"value": None, "reason": f"usage_{source}"}
        else:
            view[key] = {"value": value, "method": "exact"}
            if key == "usage_output" and source == "provider_partial":
                view[key]["partial"] = True
    k = view.get("calibration_k")
    original, forwarded = record.get("est_original_tokens"), record.get("est_forwarded_tokens")
    saved = original - forwarded if original is not None and forwarded is not None else None
    view["saving"] = _figure(*calibrated_value(saved, k))
    view["request_tokens_original"] = _figure(
        *calibrated_value(record.get("est_request_tokens_original"), k)
    )
    return view


def _figure(value: int | None, method: str) -> dict[str, Any]:
    return (
        {"value": value, "method": method}
        if value is not None
        else {
            "value": None,
            "reason": "not_measured",
        }
    )


def request_view(
    record: RequestRecord | Mapping[str, Any],
    compressors: Sequence[CompressorStatsRecord] | Sequence[Mapping[str, Any]],
    trace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    raw = asdict(record) if isinstance(record, RequestRecord) else dict(record)
    rows = [asdict(c) if isinstance(c, CompressorStatsRecord) else dict(c) for c in compressors]
    return {
        "api_version": API_VERSION,
        "request_id": raw["request_id"],
        "trace": dict(trace) if trace is not None else None,
        "record": record_view(raw),
        "compressors": rows,
    }


def compression_report(reports: Mapping[str, object]) -> EngineResult | None:
    """The compression stage's report, if the stage ran."""
    report = reports.get("transform.compression")
    return report if isinstance(report, EngineResult) else None


def compressor_summary(result: EngineResult) -> dict[str, dict[str, Any]]:
    """Per-compressor routing counts for the trace (RT-006)."""
    return {
        s.compressor_id: {
            "considered": s.considered,
            "applicable": s.applicable,
            "accepted": s.accepted,
            "saved": s.marginal_saved,
            "ms": round(s.ms_total, 3),
            "skipped": dict(s.skip_reasons),
            "cache": {"hits": s.cache_hits, "misses": s.cache_misses},
        }
        for s in result.stats
    }


def compressors_view(config: EffectiveConfig, availability: Mapping[str, str]) -> dict[str, Any]:
    """The registry as metadata (SPEC 015): spec fields, enabled, availability, the lock on its
    toggle (UI-005) and its evaluation status (UI-003). The policy is derived (CC-002)."""
    settings = config.settings.compressors.model_dump()
    enabled = {cid: bool(toggle["enabled"]) for cid, toggle in settings.items()}
    lossless = all(c.spec.kind == "LOSSLESS" for c in REGISTRY if enabled.get(c.spec.id))
    records = records_dir()
    return {
        "api_version": API_VERSION,
        "policy": "LOSSLESS_ONLY" if lossless else "LOSSY_ALLOWED",
        "compressors": [
            {
                "id": c.spec.id,
                "name": c.spec.name,
                "version": c.spec.version,
                "kind": c.spec.kind,
                "equivalence": c.spec.equivalence,
                "scope": c.spec.scope,
                "stage": c.spec.stage,
                "cost_class": c.spec.cost_class,
                "guarantees": list(c.spec.guarantees),
                "assumptions": list(c.spec.assumptions),
                "segment_kinds": sorted(str(k) for k in c.spec.segment_kinds),
                "min_tokens": c.spec.min_tokens,
                "enabled": bool(enabled.get(c.spec.id, False)),
                "default_enabled": c.spec.default_enabled,
                "availability": availability.get(c.spec.id, "available"),
                "locked_by": config.locked.get(f"compressors.{c.spec.id}.enabled"),
                "evaluation": evaluation_status(c.spec, records),
            }
            for c in REGISTRY
        ],
    }
