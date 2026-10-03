"""E9 overhead benchmark: parse + pipeline + render on synthetic agent requests.

See TOKLI_TEST_STRATEGY §8.

Usage: ``python -m benchmarks.overhead --data-dir DIR [--iterations N] [--out FILE]``.

Scenarios per size bucket. "cold": every segment text is unique in every iteration, so no cache
ever hits (worst case). "warm": the same history with a new last turn in each iteration, as when
an agent resends its conversation (the common case); the token-count and compressor-result caches
(CC-024) hit. "warm_nocache": the same with the result cache off, to show its effect. Separately,
"estimate_*" times the whole-request estimate (TM-004), which runs off the latency path and is
therefore reported, not added to the overhead. Results are reported, never gated here
(TOKLI_TEST_STRATEGY §8); ``benchmarks.compare`` applies the regression limits against the
committed baseline for the buckets the baseline contains.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from importlib import metadata
from pathlib import Path

from tokli.app.bootstrap import bootstrap
from tokli.app.measurement import whole_request_estimates
from tokli.config import CliOverrides, load_config
from tokli.domain.stage import StageContext
from tokli.protocols.anthropic_messages import parse, render

BUCKETS = {"10k": 10_000, "50k": 50_000, "200k": 200_000}
_JSON_RESULT = json.dumps(
    [
        {"id": i, "name": f"item-{i}", "tags": ["alpha", "beta"], "ok": i % 3 == 0}
        for i in range(40)
    ],
    indent=2,
)
_FILE_RESULT = "".join(f"{n:6}\tdef function_{n}(value):\n" for n in range(1, 120))


def build_request(target_tokens: int, salt: int, tail: str = "") -> bytes:
    """A Claude-Code-like conversation of roughly ``target_tokens`` (≈ 4 characters per token)."""
    messages: list[dict[str, object]] = []
    chars, turn = 0, 0
    while chars < target_tokens * 4:
        call_json, call_read = f"toolu_{salt}_{turn}_a", f"toolu_{salt}_{turn}_b"
        messages.append({"role": "user", "content": f"Step {turn} ({salt}): continue the task."})
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": call_json, "name": "mcp__api__list", "input": {}},
                    {
                        "type": "tool_use",
                        "id": call_read,
                        "name": "Read",
                        "input": {"file_path": "a.py"},
                    },
                ],
            }
        )
        json_text = _JSON_RESULT.replace("alpha", f"alpha{salt}_{turn}")
        file_text = _FILE_RESULT + f"# {salt} {turn}\n"
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call_json, "content": json_text},
                    {"type": "tool_result", "tool_use_id": call_read, "content": file_text},
                ],
            }
        )
        chars += len(json_text) + len(file_text) + 120
        turn += 1
    if tail:
        messages.append({"role": "user", "content": tail})
    body = {"model": "claude-sonnet-4-5", "max_tokens": 1024, "stream": True, "messages": messages}
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def summary(timings: list[float]) -> dict[str, object]:
    return {
        "n": len(timings),
        "p50_ms": round(statistics.median(timings), 2),
        "p95_ms": round(percentile(timings, 0.95), 2),
        "max_ms": round(max(timings), 2),
    }


def run(data_dir: str, iterations: int) -> dict[str, object]:
    def services_with(*sets: str):  # type: ignore[no-untyped-def]
        config = load_config(
            CliOverrides(data_dir=data_dir, sets=sets), dict(os.environ), sys.platform
        )
        return bootstrap(config, version="benchmark", telemetry=False)

    results: dict[str, object] = {}
    for bucket, tokens in BUCKETS.items():
        for scenario in ("cold", "warm", "warm_nocache"):
            services = services_with(
                *(("compression.result_cache_mb=0",) if scenario == "warm_nocache" else ())
            )
            timings: list[float] = []
            estimates: list[float] = []
            for i in range(iterations):
                if scenario == "cold":
                    raw = build_request(tokens, salt=1000 + i)
                else:
                    raw = build_request(tokens, salt=0, tail=f"new turn {i}")
                start = time.perf_counter()
                request = parse(raw, mutable_kinds=services.mutable_kinds)
                result = services.pipeline.run(request, StageContext(request_id=f"bench-{i}"))
                render(request, result.patches)
                timings.append((time.perf_counter() - start) * 1000)
                if scenario != "warm_nocache":
                    counter = services.selector.select(request.model)
                    estimate = whole_request_estimates(request, counter, 0)  # type: ignore[arg-type]
                    estimates.append((estimate.ended - estimate.started) * 1000)
            results[f"{bucket}_{scenario}"] = summary(timings)
            if estimates:
                results[f"{bucket}_estimate_{scenario}"] = summary(estimates)
    try:
        version = metadata.version("tokli")
    except metadata.PackageNotFoundError:
        version = "unknown"
    return {
        "benchmark": "E9 parse+pipeline+render (cold, warm, warm without result cache)",
        "tokli_version": version,
        "os": platform.system(),
        "python": platform.python_version(),
        "buckets": results,
        "vision_target": "p95 <= 25 ms for requests <= 200k tokens (a target, not a gate)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--out")
    args = parser.parse_args()
    report = run(args.data_dir, args.iterations)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
