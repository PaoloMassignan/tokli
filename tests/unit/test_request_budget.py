"""CC-014 after S8f SCR-001 (AC-CC-15 a to c): the request budget never changes a decision already
taken for a segment, and never skips a pruner."""

from __future__ import annotations

import json

from tests.helpers import FakeCounter, make_request
from tests.unit.test_duplicate_pruning import FILE, MUTABLE, conversation
from tests.unit.test_engine import Fake, run, settings_for, stats_of
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.registry import REGISTRY, build_registry
from tokli.compression.stages import CompressionStage, FeaturesStage
from tokli.domain.stage import StageContext
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage
from tokli.protocols.anthropic_messages import parse

TEXT = "a b c " * 40


class SwitchClock:
    """Advances by ``step_ms`` on every reading; tests change the step between requests."""

    def __init__(self, step_ms: float = 0.0) -> None:
        self.now = 0.0
        self.step_ms = step_ms

    def __call__(self) -> float:
        self.now += self.step_ms / 1000
        return self.now


def test_budget_never_skips_pruners() -> None:
    """AC-CC-15 (a): an exhausted budget still lets a request-scope compressor run."""

    class Selector:
        def select(self, model: str | None) -> FakeCounter:
            return FakeCounter()

    engine = Engine(
        build_registry(),
        EngineSettings(
            enabled={"duplicate_tool_results": True},
            verbatim_tools=frozenset({"Read"}),
            request_budget_ms=50,
        ),
        clock=SwitchClock(1000),  # every reading is past the budget
    )
    pipeline = Pipeline(
        [RemindersStage(), FeaturesStage(Selector()), CompressionStage(engine, Selector())]
    )
    request = parse(json.dumps(conversation(FILE, FILE)).encode(), mutable_kinds=MUTABLE)
    report = pipeline.run(request, StageContext(request_id="t")).reports["transform.compression"]
    stats = stats_of(report, "duplicate_tool_results")
    assert stats.accepted == 1
    assert stats.skipped_budget == 0 and "budget_exhausted" not in stats.skip_reasons


def test_budget_applies_cached_results() -> None:
    """AC-CC-15 (b): a segment compressed on request 1 is compressed identically on request 2,
    even when the budget is exhausted before it."""
    fake, clock = Fake(), SwitchClock(0)
    engine = Engine(
        [fake],
        settings_for("fake", result_cache_bytes=1_000_000, per_call_timeout_ms=1e9),
        clock=clock,
    )
    request = make_request(("TOOL_RESULT", TEXT), ("TOOL_RESULT", TEXT + "x"))
    first = run(engine, request)
    assert len(first.patches) == 2
    clock.step_ms = 1000
    second = run(engine, request)
    assert second.patches == first.patches
    stats = stats_of(second, "fake")
    assert stats.skipped_budget == 0 and stats.cache_hits == 2


def test_budget_skip_is_sticky() -> None:
    """AC-CC-15 (c): a segment skipped for the budget on request 1 is skipped again on request 2,
    even when budget remains, so the forwarded history does not change."""
    fake, clock = Fake(), SwitchClock(1000)
    engine = Engine(
        [fake],
        settings_for("fake", result_cache_bytes=1_000_000, per_call_timeout_ms=1e9),
        clock=clock,
    )
    request = make_request(("TOOL_RESULT", TEXT), ("TOOL_RESULT", TEXT + "x"))
    first = run(engine, request)
    assert first.patches == ()
    assert stats_of(first, "fake").skipped_budget == 2
    clock.step_ms = 0
    second = run(engine, request)
    assert second.patches == ()
    assert fake.compress_calls == 0
    stats = stats_of(second, "fake")
    assert stats.skipped_budget == 2 and stats.skip_reasons == {"budget_exhausted": 2}


def test_budget_without_cache_still_skips() -> None:
    """With the result cache off, CC-014 skips as before (nothing records the decision)."""
    fake, clock = Fake(), SwitchClock(1000)
    engine = Engine([fake], settings_for("fake", per_call_timeout_ms=1e9), clock=clock)
    request = make_request(("TOOL_RESULT", TEXT))
    assert run(engine, request).patches == ()
    clock.step_ms = 0
    assert len(run(engine, request).patches) == 1


def test_request_scope_compressors_are_cheap() -> None:
    """CC-014 (S8f SCR-001): pruners are exempt from the budget, so each must be cheap."""
    pruners = [c.spec for c in REGISTRY if c.spec.scope == "request"]
    assert pruners
    assert {s.id: s.cost_class for s in pruners} == {s.id: "cheap" for s in pruners}
