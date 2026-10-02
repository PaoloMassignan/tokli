"""Application-API views (SPEC 015, API-001, API-002, API-004). Metadata only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from tokli.compression.engine import POLICY, CompressorStats, EngineResult
from tokli.telemetry.records import CompressorStatsRecord, RequestRecord

API_VERSION = 1

__all__ = [
    "API_VERSION",
    "POLICY",
    "compression_report",
    "compressor_summary",
    "record_view",
    "request_view",
    "stats_records",
]
_ESTIMATES = ("est_original_tokens", "est_forwarded_tokens")
_UNAVAILABLE_UNTIL_S2 = (
    "est_request_tokens_original",
    "est_request_tokens_forwarded",
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
        )
        for s in stats
        if s.considered > 0
    ]


def record_view(record: Mapping[str, Any]) -> dict[str, Any]:
    """Token figures as ``{value, method}``; unavailable ones as ``{value: null, reason}``."""
    view = dict(record)
    for key in _ESTIMATES:
        value = view.get(key)
        view[key] = (
            {"value": value, "method": "estimate"}
            if value is not None
            else {"value": None, "reason": "not_measured"}
        )
    for key in _UNAVAILABLE_UNTIL_S2:
        view[key] = {"value": None, "reason": "unavailable_until_s2"}
    return view


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
        }
        for s in result.stats
    }
