"""CC-014 after S8f SCR-001 (AC-CC-15 d): on a growing conversation, the request budget never
changes the forwarded text of history already sent, whatever the timing of each request."""

from __future__ import annotations

import json
from typing import Any

from tests.helpers import FakeCounter
from tests.unit.test_request_budget import SwitchClock
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.registry import build_registry
from tokli.compression.stages import CompressionStage, FeaturesStage
from tokli.domain.models import SegmentKind
from tokli.domain.stage import StageContext
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage
from tokli.protocols.anthropic_messages import parse, render

MUTABLE = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT})
FILE = "".join(f"{n:6}\tdef synthetic_function_{n}(value):\n" for n in range(1, 60))
# Per-request clock steps: slow and fast requests alternate, as on a busy machine.
STEPS_MS = (2.0, 0.1, 3.0, 0.2, 1.0, 0.0, 2.5, 0.1, 1.5, 0.0, 3.5, 0.2)


class Selector:
    def select(self, model: str | None) -> FakeCounter:
        return FakeCounter()


def turn(i: int) -> list[dict[str, Any]]:
    listing = json.dumps(
        [{"id": n, "name": f"item-{i}-{n}", "tags": ["alpha", "beta"]} for n in range(12)],
        indent=2,
    )
    call_json, call_read = f"toolu_{i:02d}_a", f"toolu_{i:02d}_b"
    return [
        {"role": "user", "content": f"Synthetic step {i}: continue."},
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
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": call_json, "content": listing},
                {"type": "tool_result", "tool_use_id": call_read, "content": FILE + f"# {i}\n"},
            ],
        },
    ]


def test_budget_keeps_history_stable() -> None:
    clock = SwitchClock()
    engine = Engine(
        build_registry(),
        EngineSettings(
            enabled={
                "json_minify": True,
                "duplicate_tool_results": True,
                "reread_by_reference": True,
            },
            verbatim_tools=frozenset({"Read", "Bash"}),
            request_budget_ms=50,
            per_call_timeout_ms=1e9,
            result_cache_bytes=64 * 1024 * 1024,
        ),
        clock=clock,
    )
    pipeline = Pipeline(
        [RemindersStage(), FeaturesStage(Selector()), CompressionStage(engine, Selector())]
    )
    messages: list[dict[str, Any]] = []
    previous: list[Any] | None = None
    skipped = 0
    for i, step in enumerate(STEPS_MS):
        messages = messages + turn(i)
        body = {"model": "claude-test", "max_tokens": 10, "messages": messages}
        request = parse(json.dumps(body).encode(), mutable_kinds=MUTABLE)
        clock.step_ms = step
        result = pipeline.run(request, StageContext(request_id=f"r{i}"))
        report = result.reports["transform.compression"]
        skipped += sum(s.skipped_budget for s in report.stats)  # type: ignore[attr-defined]
        forwarded = json.loads(render(request, result.patches))["messages"]
        if previous is not None:
            assert forwarded[: len(previous)] == previous, f"history changed at request {i}"
        previous = forwarded
    assert skipped > 0  # the budget really was exhausted on some requests
