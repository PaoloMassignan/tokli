"""SPEC 007 pipeline (fixed stage list, C2), the reminders analyzer, features and span checks."""

from __future__ import annotations

from typing import Literal

import pytest

from tests.helpers import FakeCounter, make_request
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.registry import REGISTRY
from tokli.compression.stages import CompressionStage, FeaturesStage
from tokli.domain.models import CanonicalRequest, Patch, Span
from tokli.domain.spans import spans_preserved
from tokli.domain.stage import StageContext, StageResult, StageView
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage

CTX = StageContext(request_id="01TEST")
PRETTY = '{\n  "items": [\n    {"id": 1, "name": "alpha"},\n    {"id": 2, "name": "beta"}\n  ]\n}'


class FixedSelector:
    def select(self, model: str | None) -> FakeCounter:
        return FakeCounter()


def default_stages() -> list[object]:
    selector = FixedSelector()
    engine = Engine(
        REGISTRY, EngineSettings(enabled={"json_minify": True}, verbatim_tools=frozenset())
    )
    return [RemindersStage(), FeaturesStage(selector), CompressionStage(engine, selector)]  # type: ignore[arg-type]


class Raising:
    id = "transform.raising"
    kind: Literal["transformer"] = "transformer"

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult:
        raise RuntimeError("stage bug")


class Upper:
    """A test-only transformer: uppercases every USER_TEXT segment."""

    id = "transform.upper"
    kind: Literal["transformer"] = "transformer"

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult:
        return StageResult(
            patches=[
                Patch(s.id, view.texts[s.id].upper(), (self.id,))
                for s in request.segments
                if s.mutable and s.kind == "USER_TEXT"
            ]
        )


class PatchingAnalyzer:
    id = "analyze.bad"
    kind: Literal["analyzer"] = "analyzer"

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult:
        return StageResult(patches=[Patch("s0", "changed", (self.id,))])


def test_default_stage_list() -> None:
    assert Pipeline(default_stages()).stage_ids == (  # type: ignore[arg-type]
        "analyze.reminders",
        "analyze.features",
        "transform.compression",
    )


def test_pipeline_runs_compression() -> None:
    request = make_request(("TOOL_RESULT", PRETTY))
    result = Pipeline(default_stages()).run(request, CTX)  # type: ignore[arg-type]
    assert [p.produced_by for p in result.patches] == [("json_minify",)]
    assert [o.stage_id for o in result.outcomes] == list(Pipeline(default_stages()).stage_ids)  # type: ignore[arg-type]
    assert all(o.status == "ok" for o in result.outcomes)
    assert "transform.compression" in result.reports


def test_stage_exception_isolated() -> None:
    request = make_request(("USER_TEXT", "hello there " * 10))
    result = Pipeline([Raising(), Upper()]).run(request, CTX)
    assert [(o.stage_id, o.status, o.reason) for o in result.outcomes] == [
        ("transform.raising", "error", "stage_exception(transform.raising)"),
        ("transform.upper", "ok", ""),
    ]
    assert [p.new_text for p in result.patches] == ["HELLO THERE " * 10]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.6  # every reading advances 600 ms
        return self.now


def test_stage_timeout_isolated() -> None:
    request = make_request(("USER_TEXT", "hello there " * 10))
    result = Pipeline([Upper()], stage_budget_ms=500, clock=Clock()).run(request, CTX)
    assert result.outcomes[0].status == "error"
    assert result.outcomes[0].reason == "stage_timeout(transform.upper)"
    assert result.patches == ()


def test_analyzer_cannot_patch() -> None:
    request = make_request(("USER_TEXT", "hello"))
    result = Pipeline([PatchingAnalyzer()]).run(request, CTX)
    assert result.outcomes[0].status == "error"
    assert result.outcomes[0].reason == "analyzer_returned_patches"
    assert result.patches == ()


def test_new_transformer_needs_no_adapter_change() -> None:
    # A test-only transformer is inserted without touching adapters or compressors (PL-007);
    # the end-to-end variant through the Anthropic adapter lives in the compat suite.
    request = make_request(("USER_TEXT", "abc " * 20), ("TOOL_RESULT", PRETTY))
    result = Pipeline([RemindersStage(), Upper()]).run(request, CTX)
    assert [p.segment_id for p in result.patches] == ["s0"]


def test_transformer_patch_breaking_protected_span_is_dropped() -> None:
    text = "<system-reminder>keep me</system-reminder> and lowercase text"
    request = make_request(("USER_TEXT", text))
    result = Pipeline([RemindersStage(), Upper()]).run(request, CTX)
    assert result.patches == ()
    assert result.outcomes[1].reason == "protected_span_changed"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a <system-reminder>x</system-reminder> b", ["<system-reminder>x</system-reminder>"]),
        (
            "<system-reminder>one</system-reminder> mid "
            "<system-reminder>two\nlines</system-reminder>",
            [
                "<system-reminder>one</system-reminder>",
                "<system-reminder>two\nlines</system-reminder>",
            ],
        ),
        ("<system-reminder>unclosed", []),
        (
            "<system-reminder>a <system-reminder>b</system-reminder> c</system-reminder>",
            ["<system-reminder>a <system-reminder>b</system-reminder>"],
        ),
        ("<System-Reminder>x</System-Reminder>", []),
    ],
)
def test_reminder_spans_protected(text: str, expected: list[str]) -> None:
    request = make_request(("USER_TEXT", text), ("TOOL_RESULT", text))
    view = StageView(texts={s.id: s.text for s in request.segments}, spans={}, features={})
    result = RemindersStage().run(request, view, CTX)
    for sid in ("s0", "s1"):
        spans = result.protected_spans.get(sid, [])
        assert [text[s.start : s.end] for s in spans] == expected
        assert all(s.reason == "system-reminder" for s in spans)


def test_features_stage_counts_and_json_candidate() -> None:
    request = make_request(("TOOL_RESULT", "  [1, 2]  "), ("USER_TEXT", "plain"))
    view = StageView(texts={s.id: s.text for s in request.segments}, spans={}, features={})
    result = FeaturesStage(FixedSelector()).run(request, view, CTX)  # type: ignore[arg-type]
    assert (
        result.features["s0"].tokens == len("  [1, 2]  ") and result.features["s0"].json_candidate
    )
    assert not result.features["s1"].json_candidate


@pytest.mark.parametrize(
    ("original", "spans", "new", "expected"),
    [
        ("aXbYc", [Span(1, 2, "r"), Span(3, 4, "r")], "XY", True),
        ("aXbYc", [Span(1, 2, "r"), Span(3, 4, "r")], "YX", False),
        ("aXbYc", [Span(1, 2, "r")], "abc", False),
        ("same", [], "anything", True),
        ("aXXb", [Span(1, 2, "r"), Span(2, 3, "r")], "X", False),
    ],
)
def test_spans_preserved(original: str, spans: list[Span], new: str, expected: bool) -> None:
    assert spans_preserved(original, spans, new) is expected


class Suffix:
    """A second test transformer that records what it saw."""

    id = "transform.suffix"
    kind: Literal["transformer"] = "transformer"

    def __init__(self) -> None:
        self.seen: dict[str, str] = {}

    def run(self, request: CanonicalRequest, view: StageView, ctx: StageContext) -> StageResult:
        self.seen = dict(view.texts)
        return StageResult(patches=[Patch("s0", view.texts["s0"] + "!", (self.id,))])


def test_patches_visible_to_later_stages() -> None:
    request = make_request(("USER_TEXT", "hello there " * 10))
    later = Suffix()
    result = Pipeline([Upper(), later]).run(request, CTX)
    assert later.seen["s0"] == "HELLO THERE " * 10  # the second stage saw the first one's patch
    assert result.patches[0].new_text == "HELLO THERE " * 10 + "!"
    assert result.patches[0].produced_by == ("transform.upper", "transform.suffix")


def test_features_linear_time() -> None:
    import time

    # RT-001: linear in the *length* of a segment: one segment of 0.5 MB vs 5 MB, with a counter
    # that is itself O(n), so the measured cost is dominated by work proportional to the text.
    class LinearCounter:
        tokenizer_id = "linear"

        def count(self, text: str) -> int:
            return text.count(" ")

    class Selector:
        def select(self, model: str | None) -> LinearCounter:
            return LinearCounter()

    stage = FeaturesStage(Selector())  # type: ignore[arg-type]

    def elapsed(size: int) -> float:
        text = "  [" + ", ".join(['{"k": "v v v"}'] * (size // 16)) + "]  "
        request = make_request(("TOOL_RESULT", text))
        view = StageView(texts={"s0": text}, spans={}, features={})
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            stage.run(request, view, CTX)
            best = min(best, time.perf_counter() - start)
        return best

    # SCR-001: 5 MB and 50 MB are both larger than CPU caches, so the ratio reflects the algorithm.
    elapsed(1_000_000)  # warm-up
    assert elapsed(50_000_000) / max(elapsed(5_000_000), 1e-6) <= 15
