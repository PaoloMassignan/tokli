"""Metrics query time on a large synthetic telemetry database (S3, I6; reported, never gated).

Usage: ``python -m benchmarks.metrics --rows 100000 [--out FILE]``. Builds a database in a temporary
directory with ``rows`` requests over 30 days (one compressor row each), then times each metrics
use case a few times.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import sqlite3
import statistics
import tempfile
import time
from dataclasses import asdict, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tokli.app.metrics import MetricsQuery, parse_filters
from tokli.telemetry.records import CompressorStatsRecord, RequestRecord
from tokli.telemetry.store import TelemetryStore


def build(path: Path, rows: int) -> None:
    store = TelemetryStore(path, retention_days=0)
    store.start()  # creates the current schema
    store.close()
    rng = random.Random(7)
    end = datetime.now(UTC)
    request_columns = [f.name for f in fields(RequestRecord)]
    stats_columns = [f.name for f in fields(CompressorStatsRecord)]
    requests, stats = [], []
    for i in range(rows):
        ts = end - timedelta(seconds=rng.uniform(0, 30 * 86400))
        compressed = rng.random() < 0.3
        original = rng.randint(1_000, 150_000)
        saved = rng.randint(10, 2_000) if compressed else 0
        rid = f"01BENCH{i:019d}"
        record = RequestRecord(
            request_id=rid,
            ts_start=ts.isoformat(timespec="milliseconds"),
            ts_end=ts.isoformat(timespec="milliseconds"),
            provider="anthropic",
            protocol="anthropic_messages",
            endpoint="/v1/messages",
            model=rng.choice(["claude-a", "claude-b"]),
            stream=True,
            auth_mode="passthrough",
            credential_kind="oauth",
            policy="LOSSLESS_ONLY",
            config_hash="bench",
            outcome="compressed" if compressed else "passthrough",
            passthrough_reason=None if compressed else "no_applicable_compressor",
            segments_total=50,
            segments_mutable=20,
            segments_changed=1 if compressed else 0,
            tokenizer_id="tiktoken:o200k_base@bench",
            est_original_tokens=500,
            est_forwarded_tokens=500 - saved,
            status_code=200,
            ms_parse=0.5,
            ms_pipeline=1.0,
            ms_render=0.3,
            ms_upstream_ttfb=800.0,
            ms_upstream_total=5000.0,
            ms_tokli_overhead=rng.uniform(1, 20),
            ms_total=5010.0,
            est_request_tokens_original=original,
            est_request_tokens_forwarded=original - saved,
            usage_source="provider",
            usage_input=rng.randint(1, 50),
            usage_cache_read=int(original * 1.4),
            usage_cache_write_5m=rng.randint(0, 3_000),
            usage_cache_write_1h=0,
            usage_output=rng.randint(10, 500),
            calibration_k=rng.uniform(1.2, 1.6),
            header_names=("anthropic-version", "authorization"),
        )
        row = asdict(record)
        row["header_names"] = json.dumps(list(row["header_names"]))
        requests.append([row[c] for c in request_columns])
        stat = CompressorStatsRecord(
            request_id=rid,
            compressor_id="bench_compressor",
            compressor_version="1",
            kind="LOSSLESS",
            considered=20,
            applicable=2 if compressed else 0,
            accepted=1 if compressed else 0,
            rejected_no_gain=1 if compressed else 0,
            rejected_invariant=0,
            failed=0,
            skipped_budget=0,
            tokens_in=900 if compressed else 0,
            tokens_out=900 - saved if compressed else 0,
            marginal_saved=saved,
            ms_total=0.2,
            tokens_in_accepted=600 if compressed else 0,
        )
        values = asdict(stat)
        values["skip_reasons"] = "{}"
        stats.append([values[c] for c in stats_columns])
    with sqlite3.connect(path) as db:
        db.executemany(
            f"INSERT INTO requests ({', '.join(request_columns)}) "
            f"VALUES ({', '.join('?' for _ in request_columns)})",
            requests,
        )
        db.executemany(
            f"INSERT INTO compressor_stats ({', '.join(stats_columns)}) "
            f"VALUES ({', '.join('?' for _ in stats_columns)})",
            stats,
        )


def timed(run, repeat: int = 5) -> dict[str, float]:  # type: ignore[no-untyped-def]
    values = []
    for _ in range(repeat):
        start = time.perf_counter()
        run()
        values.append((time.perf_counter() - start) * 1000)
    return {"median_ms": round(statistics.median(values), 1), "max_ms": round(max(values), 1)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--out")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tokli.db"
        build(path, args.rows)
        query = MetricsQuery(path)
        week = parse_filters({"tz": "Europe/Rome"})
        month = parse_filters(
            {
                "from": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
                "tz": "Europe/Rome",
                "bucket": "day",
            }
        )
        report = {
            "benchmark": "metrics queries on a synthetic database (reported, not gated)",
            "rows": args.rows,
            "os": platform.system(),
            "python": platform.python_version(),
            "summary_7d": timed(lambda: query.summary(week)),
            "summary_30d": timed(lambda: query.summary(month)),
            "timeseries_7d_hour": timed(lambda: query.timeseries(week)),
            "timeseries_30d_day": timed(lambda: query.timeseries(month)),
            "compressors_30d": timed(lambda: query.compressors(month)),
            "requests_page": timed(lambda: query.requests(50, None)),
        }
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
