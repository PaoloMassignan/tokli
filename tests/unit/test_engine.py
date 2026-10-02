"""SPEC 009 engine (S1 subset): policy, filters, acceptance gate, invariants, isolation, stats."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import FakeCounter, make_request, view_of
from tokli.compression.contract import Applicability, SegmentView
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.registry import REGISTRY
from tokli.compressors.json_minify import SPEC as JSON_SPEC
from tokli.compressors.json_minify import JsonMinify
from tokli.domain.models import Span
from tokli.domain.stage import Features

ROOT = Path(__file__).resolve().parents[2]
PRETTY = (
    '{\n  "items": [\n    {"id": 1, "name": "alpha"},\n    {"id": 2, "name": "beta"}\n  ],'
    '\n  "total": 2\n}'
)


def settings_for(*enabled: str, **overrides: object) -> EngineSettings:
    base = EngineSettings(
        enabled={name: True for name in enabled},
        verbatim_tools=frozenset({"Read", "Bash"}),
    )
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


class Fake:
    """A configurable fake compressor."""

    def __init__(
        self,
        cid: str = "fake",
        kind: str = "LOSSLESS",
        transform: Callable[[str], str | None] = lambda t: t.replace(" ", ""),
        applicable: bool = True,
        requires: tuple[str, ...] = (),
        decode: Callable[[str], str] | None = None,
    ) -> None:
        self.spec = dataclasses.replace(
            JSON_SPEC,
            id=cid,
            kind=kind,
            requires=requires,
            stage="domain",  # type: ignore[arg-type]
        )
        self._transform = transform
        self._applicable = applicable
        self._decode = decode or (lambda t: t)
        self.applicable_calls = 0
        self.compress_calls = 0

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability:
        self.applicable_calls += 1
        return Applicability(self._applicable, "" if self._applicable else "nope")

    def compress(self, text: str, view: SegmentView) -> str | None:
        self.compress_calls += 1
        return self._transform(text)

    def decode(self, text: str) -> str:
        return self._decode(text)

    def equivalent(self, original: str, decoded: str) -> bool:
        return original.replace(" ", "") == decoded.replace(" ", "")


def run(engine: Engine, request, spans=None):  # type: ignore[no-untyped-def]
    return engine.run(request, view_of(request, spans=spans), FakeCounter())


def stats_of(result, cid: str):  # type: ignore[no-untyped-def]
    return next(s for s in result.stats if s.compressor_id == cid)


def test_lossless_only_never_runs_lossy_compressor() -> None:
    lossy, unknown, selective = (
        Fake("lossy", kind="LOSSY"),
        Fake("unk", kind="UNKNOWN"),
        Fake("sel", kind="SELECTIVE"),
    )
    engine = Engine([lossy, unknown, selective], settings_for("lossy", "unk", "sel"))
    result = run(engine, make_request(("TOOL_RESULT", "x " * 100)))
    assert lossy.applicable_calls == lossy.compress_calls == 0
    assert unknown.compress_calls == selective.compress_calls == 0
    assert stats_of(result, "lossy").skip_reasons == {"policy_forbids(LOSSY)": 1}
    assert result.patches == ()


def test_disabled_compressor_skipped() -> None:
    fake = Fake()
    result = run(Engine([fake], settings_for()), make_request(("TOOL_RESULT", "x " * 100)))
    assert fake.applicable_calls == 0
    assert stats_of(result, "fake").skip_reasons == {"disabled": 1}


def test_enabled_compressor_not_applied_when_not_applicable() -> None:
    fake = Fake(applicable=False)
    result = run(Engine([fake], settings_for("fake")), make_request(("TOOL_RESULT", "x " * 100)))
    assert fake.applicable_calls == 1 and fake.compress_calls == 0
    assert stats_of(result, "fake").skip_reasons == {"not_applicable(nope)": 1}
    assert stats_of(result, "fake").applicable == 0


def test_cheap_filters_before_applicable() -> None:
    fake = Fake()
    request = make_request(
        ("TOOL_RESULT", "x " * 10),  # too small
        ("TOOL_RESULT", "x " * 100),  # verbatim tool
        ("ASSISTANT_TEXT", "x " * 100),  # kind not supported / not mutable
        tool_names=("SomeTool", "Read", None),
    )
    result = run(Engine([fake], settings_for("fake")), request)
    assert fake.applicable_calls == 0
    assert stats_of(result, "fake").skip_reasons == {"too_small": 1, "verbatim_tool": 1}


def test_min_segment_tokens_default() -> None:
    assert EngineSettings(enabled={}, verbatim_tools=frozenset()).min_segment_tokens == 64
    fake = Fake(transform=lambda t: t[:-10])
    engine = Engine([fake], settings_for("fake"))
    assert run(engine, make_request(("TOOL_RESULT", "y" * 63))).patches == ()
    assert len(run(engine, make_request(("TOOL_RESULT", "y" * 64))).patches) == 1


def test_json_minify_skipped_for_verbatim_tool() -> None:
    request = make_request(("TOOL_RESULT", PRETTY), tool_names=("Read",))
    result = run(Engine(REGISTRY, settings_for("json_minify")), request)
    assert result.patches == ()
    assert stats_of(result, "json_minify").skip_reasons == {"verbatim_tool": 1}


def test_unresolved_tool_name_treated_as_verbatim() -> None:
    request = make_request(("TOOL_RESULT", PRETTY), tool_names=(None,))
    result = run(Engine(REGISTRY, settings_for("json_minify")), request)
    assert result.patches == ()
    assert stats_of(result, "json_minify").skip_reasons == {"verbatim_tool": 1}
    detail = next(i for i in result.invocations if i.compressor_id == "json_minify")
    assert detail.reason == "verbatim_tool(unresolved)"


def test_json_minify_applied_through_engine() -> None:
    request = make_request(("TOOL_RESULT", PRETTY))
    result = run(Engine(REGISTRY, settings_for("json_minify")), request)
    assert len(result.patches) == 1
    patch = result.patches[0]
    assert patch.produced_by == ("json_minify",)
    assert json.loads(patch.new_text) == json.loads(PRETTY)
    stats = stats_of(result, "json_minify")
    assert (stats.considered, stats.applicable, stats.accepted) == (1, 1, 1)
    assert stats.marginal_saved == len(PRETTY) - len(patch.new_text)


def test_longer_output_rejected() -> None:
    fake = Fake(transform=lambda t: t + "more")
    result = run(Engine([fake], settings_for("fake")), make_request(("TOOL_RESULT", "x " * 100)))
    assert result.patches == ()
    assert stats_of(result, "fake").rejected_no_gain == 1


def test_below_min_gain_rejected() -> None:
    fake = Fake(transform=lambda t: t[:-3])  # saves 3 < min_gain_tokens 4
    result = run(Engine([fake], settings_for("fake")), make_request(("TOOL_RESULT", "x" * 100)))
    assert result.patches == ()
    assert stats_of(result, "fake").rejected_no_gain == 1


def test_protected_span_change_rejected() -> None:
    text = "keep <system-reminder>do not touch</system-reminder> " + "x " * 50
    start = text.index("<system-reminder>")
    end = text.index("</system-reminder>") + len("</system-reminder>")
    fake = Fake(transform=lambda t: t.replace("touch", "tch").replace(" ", ""))
    request = make_request(("USER_TEXT", text))
    result = run(
        Engine([fake], settings_for("fake")), request, spans={"s0": [Span(start, end, "reminder")]}
    )
    assert result.patches == ()
    assert stats_of(result, "fake").rejected_invariant == 1


def test_compressor_exception_is_recorded() -> None:
    def boom(text: str) -> str:
        raise RuntimeError("bug")

    result = run(
        Engine([Fake(transform=boom)], settings_for("fake")),
        make_request(("TOOL_RESULT", "x " * 100)),
    )
    assert result.patches == ()
    assert stats_of(result, "fake").failed == 1
    assert [i.reason for i in result.invocations] == ["exception"]


class StepClock:
    """A clock that advances by a fixed step on every call (ms → seconds)."""

    def __init__(self, step_ms: float) -> None:
        self.now = 0.0
        self.step = step_ms / 1000

    def __call__(self) -> float:
        self.now += self.step
        return self.now


def test_compressor_timeout_is_recorded() -> None:
    engine = Engine(
        [Fake()],
        settings_for("fake", per_call_timeout_ms=5, request_budget_ms=10_000),
        clock=StepClock(10),
    )
    result = run(engine, make_request(("TOOL_RESULT", "x " * 100)))
    assert result.patches == ()
    assert stats_of(result, "fake").failed == 1
    assert [i.reason for i in result.invocations] == ["timeout"]


def test_late_result_discarded_as_timeout() -> None:
    fake = Fake()
    engine = Engine(
        [fake],
        settings_for("fake", per_call_timeout_ms=5, request_budget_ms=10_000),
        clock=StepClock(10),
    )
    result = run(engine, make_request(("TOOL_RESULT", "x " * 100)))
    assert fake.compress_calls == 1  # it ran to completion …
    assert result.patches == ()  # … but its late result was discarded


def test_budget_exhaustion_skips() -> None:
    engine = Engine(
        [Fake()],
        settings_for("fake", request_budget_ms=15, per_call_timeout_ms=10_000),
        clock=StepClock(10),
    )
    request = make_request(*[("TOOL_RESULT", "x " * 100)] * 4)
    stats = stats_of(run(engine, request), "fake")
    assert stats.skipped_budget >= 1
    assert stats.skip_reasons.get("budget_exhausted", 0) == stats.skipped_budget


def test_missing_dependency_marks_compressor_unavailable() -> None:
    fake = Fake(requires=("not_a_module_tokli",))
    engine = Engine([fake], settings_for("fake"))
    assert engine.availability() == {"fake": "unavailable(not_a_module_tokli)"}
    result = run(engine, make_request(("TOOL_RESULT", "x " * 100)))
    assert fake.applicable_calls == 0
    assert stats_of(result, "fake").skip_reasons == {"unavailable(not_a_module_tokli)": 1}


def test_verify_lossless_rejects_decode_mismatch() -> None:
    fake = Fake(transform=lambda t: t.replace(" ", ""), decode=lambda t: t + "!")
    result = run(
        Engine([fake], settings_for("fake", verify_lossless=True)),
        make_request(("TOOL_RESULT", "x " * 100)),
    )
    assert result.patches == ()
    assert [i.reason for i in result.invocations] == ["decode_mismatch"]


def test_compressor_stats_expected_fixture() -> None:
    request = make_request(
        ("TOOL_RESULT", PRETTY),
        ("TOOL_RESULT", "plain words " * 10),
        ("USER_TEXT", "short"),
    )
    result = run(Engine(REGISTRY, settings_for("json_minify")), request)
    stats = stats_of(result, "json_minify")
    minified = result.patches[0].new_text
    assert (stats.considered, stats.applicable, stats.accepted) == (3, 1, 1)
    assert stats.skip_reasons == {"not_applicable(not_json)": 1, "too_small": 1}
    assert (stats.tokens_in, stats.tokens_out) == (len(PRETTY), len(minified))
    assert result.segments_mutable == 3 and result.segments_changed == 1
    assert result.est_original_tokens - result.est_forwarded_tokens == stats.marginal_saved


def test_segment_output_independent_of_other_segments() -> None:
    engine = Engine(REGISTRY, settings_for("json_minify"))
    alone = run(engine, make_request(("TOOL_RESULT", PRETTY))).patches[0].new_text
    others = [("TOOL_RESULT", f'{{ "n": {i},  "v": "{"z" * i}" }}') for i in range(50)]
    mixed = run(engine, make_request(*others[:20], ("TOOL_RESULT", PRETTY), *others[20:]))
    assert [p.new_text for p in mixed.patches if p.segment_id == "s20"] == [alone]


TEXTS = st.lists(
    st.one_of(st.text(min_size=0, max_size=300), st.just(PRETTY), st.just("[\n 1,\n 2\n]" * 30)),
    min_size=1,
    max_size=6,
)


@settings(max_examples=150, deadline=None)
@given(TEXTS)
def prop_compression_never_increases_tokens(texts: list[str]) -> None:
    request = make_request(*[("TOOL_RESULT", t) for t in texts])
    result = run(Engine(REGISTRY, settings_for("json_minify")), request)
    counter = FakeCounter()
    for patch in result.patches:
        assert counter.count(patch.new_text) <= counter.count(
            request.segment(patch.segment_id).text
        )
    assert result.est_forwarded_tokens <= result.est_original_tokens


@settings(max_examples=100, deadline=None)
@given(TEXTS)
def prop_compression_is_deterministic(texts: list[str]) -> None:
    request = make_request(*[("TOOL_RESULT", t) for t in texts])
    first = run(Engine(REGISTRY, settings_for("json_minify")), request)
    second = run(Engine(REGISTRY, settings_for("json_minify")), request)
    assert first.patches == second.patches


@settings(max_examples=100, deadline=None)
@given(TEXTS)
def prop_marginal_savings_sum_to_total(texts: list[str]) -> None:
    request = make_request(*[("TOOL_RESULT", t) for t in texts])
    result = run(Engine(REGISTRY, settings_for("json_minify")), request)
    total = sum(s.marginal_saved for s in result.stats)
    assert total == result.est_original_tokens - result.est_forwarded_tokens


@settings(max_examples=100, deadline=None)
@given(
    st.text(min_size=0, max_size=80),
    st.text(min_size=1, max_size=30),
    st.text(min_size=0, max_size=80),
)
def prop_protected_spans_preserved(before: str, protected: str, after: str) -> None:
    text = before + protected + after + " x" * 40
    span = Span(len(before), len(before) + len(protected), "test")
    fake = Fake(transform=lambda t: t.replace(" ", "")[: max(0, len(t) // 2)])
    request = make_request(("USER_TEXT", text))
    result = run(Engine([fake], settings_for("fake")), request, spans={"s0": [span]})
    for patch in result.patches:
        assert protected in patch.new_text


def test_registry_contract_every_lossless_has_roundtrip_property() -> None:
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "tests").rglob("test_*.py"))
    for compressor in REGISTRY:
        if compressor.spec.kind == "LOSSLESS":
            name = f"prop_{compressor.spec.id}_decode_roundtrip"
            assert f"def {name}(" in sources, name


def test_every_compressor_declares_assumptions() -> None:
    for compressor in REGISTRY:
        assert compressor.spec.assumptions, compressor.spec.id


def test_registry_default_enabled_requires_eval_record() -> None:
    for compressor in REGISTRY:
        if not compressor.spec.default_enabled:
            continue
        path = ROOT / "evals" / "records" / f"{compressor.spec.id}.yaml"
        assert path.is_file(), path
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert record["compressor"] == compressor.spec.id
        assert str(record["version"]) == compressor.spec.version
        assert set(record["assumptions_covered"]) >= set(compressor.spec.assumptions)
        if record["tier"] == "provisional":
            assert (
                compressor.spec.id == "json_minify"
            )  # QE-016: the only provisional record allowed
        else:
            assert record["verdict"] == "no_measurable_damage"


def test_json_minify_is_the_only_registered_compressor_in_s1() -> None:
    assert [c.spec.id for c in REGISTRY] == ["json_minify"]
    assert isinstance(REGISTRY[0], JsonMinify)


@pytest.mark.parametrize("cid", [c.spec.id for c in REGISTRY])
def test_registered_compressors_are_available(cid: str) -> None:
    assert Engine(REGISTRY, settings_for(cid)).availability()[cid] == "available"
