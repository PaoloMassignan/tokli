"""Regression limits for the E9 benchmark (TOKLI_TEST_STRATEGY §8; POLICY, provisional).

Usage: ``python -m benchmarks.compare CURRENT.json BASELINE.json``. Compares p95 per bucket:
warns above 1.25x the baseline, fails above 2x the baseline. Absolute milliseconds are never a gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WARN, FAIL = 1.25, 2.0


def main(argv: list[str]) -> int:
    current = json.loads(Path(argv[0]).read_text(encoding="utf-8"))["buckets"]
    baseline = json.loads(Path(argv[1]).read_text(encoding="utf-8"))["buckets"]
    status = 0
    for bucket, base in baseline.items():
        now = current[bucket]["p95_ms"]
        ratio = now / base["p95_ms"] if base["p95_ms"] else 1.0
        level = "ok"
        if ratio > FAIL:
            level, status = "FAIL", 1
        elif ratio > WARN:
            level = "warn"
        print(f"{bucket}: p95 {now} ms vs baseline {base['p95_ms']} ms ({ratio:.2f}x) {level}")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
