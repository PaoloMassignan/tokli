"""SPEC 019 `duplicate_tool_results` (S4), CM-013 tool records, and the engine's request scope,
reference integrity (CC-019), chains (CC-009) and enable-only gating (CC-002 after S4 SCR-001)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import FakeCounter
from tokli.compression.contract import Applicability, SegmentRef, SegmentView
from tokli.compression.engine import Engine, EngineResult, EngineSettings
from tokli.compression.registry import REGISTRY, build_registry
from tokli.compression.stages import CompressionStage, FeaturesStage
from tokli.compressors.duplicate_tool_results import STUB_PREFIX, DuplicateToolResults
from tokli.compressors.json_minify import SPEC as JSON_SPEC
from tokli.domain.models import CanonicalRequest, SegmentKind
from tokli.domain.stage import Features, StageContext
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage
from tokli.protocols.anthropic_messages import parse, render

MUTABLE = frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT})
FIXTURES = Path(__file__).resolve().parents[1] / "compat" / "fixtures" / "anthropic_messages"
FILE = "".join(f"{n:6}\tline number {n} of a synthetic file\n" for n in range(1, 12))
OTHER = "".join(f"{n:6}\tanother synthetic file, line {n}\n" for n in range(1, 12))
REMINDER = "<system-reminder>\nA synthetic reminder.\n</system-reminder>"


class Selector:
    def select(self, model: str | None) -> FakeCounter:
        return FakeCounter()


def conversation(
    *results: Any, tool: str = "Read", text_after: str | None = None
) -> dict[str, Any]:
    """One assistant tool call per result, each answered in the next user turn. A result is a
    string, a list of content blocks, or a dict ``{"content": ..., **block attrs}``."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": "start the synthetic task"}]
    for i, result in enumerate(results):
        call = f"toolu_{i:02d}"
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": call,
                        "name": tool,
                        "input": {"file_path": f"f{i}.py"},
                    }
                ],
            }
        )
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call}
        if isinstance(result, dict):
            block.update(result)
        else:
            block["content"] = result
        content: list[dict[str, Any]] = [block]
        if text_after and i == len(results) - 1:
            content.append({"type": "text", "text": text_after})
        messages.append({"role": "user", "content": content})
    return {"model": "claude-test", "max_tokens": 10, "messages": messages}


def pipeline(
    enabled: dict[str, bool],
    *,
    require_same_call: bool = False,
    extra: tuple[Any, ...] = (),
    verify: bool = True,
) -> Pipeline:
    registry = (
        *build_registry(duplicate_min_tokens=64, duplicate_require_same_call=require_same_call),
        *extra,
    )
    engine = Engine(
        registry,
        EngineSettings(
            enabled=enabled, verbatim_tools=frozenset({"Read", "Bash"}), verify_lossless=verify
        ),
    )
    selector = Selector()
    return Pipeline([RemindersStage(), FeaturesStage(selector), CompressionStage(engine, selector)])


BOTH = {"duplicate_tool_results": True, "json_minify": True}
DUP = {"duplicate_tool_results": True}


def run(
    body: dict[str, Any], enabled: dict[str, bool] = DUP, **kw: Any
) -> tuple[CanonicalRequest, EngineResult, dict[str, Any]]:
    request = parse(json.dumps(body).encode(), mutable_kinds=MUTABLE)
    result = pipeline(enabled, **kw).run(request, StageContext(request_id="t"))
    report = result.reports["transform.compression"]
    assert isinstance(report, EngineResult)
    return request, report, json.loads(render(request, result.patches))


def results_of(body: dict[str, Any]) -> list[Any]:
    return [
        block["content"]
        for message in body["messages"]
        if message["role"] == "user" and isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]


def refs_of(request: CanonicalRequest) -> list[SegmentRef]:
    return [
        SegmentRef(
            s.id,
            SegmentView(s.kind, s.role, s.tool_name, s.is_error, ()),
            s.tool_call_id,
            s.whole_result,
        )
        for s in request.segments
    ]


def stub_for(call: str, original: str) -> str:
    return f"{STUB_PREFIX}{call} earlier in this conversation — {len(original)} tokens omitted]"


# -- CM-013 -----------------------------------------------------------------------------------


def test_tool_records_exposed_read_only() -> None:
    request = parse(json.dumps(conversation(FILE, OTHER)).encode(), mutable_kinds=MUTABLE)
    assert [(t.call_id, t.name, t.arguments, t.index) for t in request.tools] == [
        ("toolu_00", "Read", {"file_path": "f0.py"}, 0),
        ("toolu_01", "Read", {"file_path": "f1.py"}, 1),
    ]
    results = [s for s in request.segments if s.kind is SegmentKind.TOOL_RESULT]
    assert [t.result_segment_ids for t in request.tools] == [(results[0].id,), (results[1].id,)]
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.tools[0].name = "Write"  # type: ignore[misc]


# -- PR-002/003, AC-PR-1 ----------------------------------------------------------------------


def test_duplicate_results_stub_later_copies() -> None:
    body = conversation(FILE, FILE, FILE)
    request, result, forwarded = run(body)
    assert results_of(forwarded) == [FILE, stub_for("toolu_00", FILE), stub_for("toolu_00", FILE)]
    assert result.reference_stubs == 2
    refs = [s for s in request.segments if s.kind is SegmentKind.TOOL_RESULT]
    sent = dict(zip((s.id for s in refs), results_of(forwarded), strict=True))
    decoded = DuplicateToolResults().decode_request(sent, refs_of(request))
    assert decoded == {refs[1].id: FILE, refs[2].id: FILE}


def test_duplicate_pruning_never_stubs_first_occurrence() -> None:
    _, _, forwarded = run(conversation(OTHER, FILE, OTHER, FILE))
    assert results_of(forwarded)[:2] == [OTHER, FILE]
    assert results_of(forwarded)[2:] == [stub_for("toolu_00", OTHER), stub_for("toolu_01", FILE)]


def test_duplicate_stub_names_earliest_copy() -> None:
    _, _, forwarded = run(conversation(FILE, OTHER, FILE, FILE))
    assert results_of(forwarded)[2] == results_of(forwarded)[3] == stub_for("toolu_00", FILE)


def test_small_duplicates_not_stubbed() -> None:
    small = "tiny result"
    _, result, forwarded = run(conversation(small, small))
    assert results_of(forwarded) == [small, small] and result.reference_stubs == 0


POOL = [FILE, OTHER, FILE.upper(), "x" * 80, REMINDER + "\n" + FILE]


@settings(max_examples=120, deadline=None)
@given(st.lists(st.sampled_from(POOL), min_size=1, max_size=8))
def prop_duplicate_pruning_decodes_whole_request(texts: list[str]) -> None:
    """PR-003 / CC-015 (reference): decoding the whole forwarded request restores every original
    text, and every stub names an earlier, unstubbed result."""
    request, _, forwarded = run(conversation(*texts))
    sent = results_of(forwarded)
    refs = [s for s in request.segments if s.kind is SegmentKind.TOOL_RESULT]
    texts_by_id = {s.id: t for s, t in zip(refs, sent, strict=True)}
    decoded = DuplicateToolResults().decode_request(texts_by_id, refs_of(request))
    restored = [decoded.get(s.id, texts_by_id[s.id]) for s in refs]
    assert restored == texts
    for i, text in enumerate(sent):
        if text.startswith(STUB_PREFIX):
            target = int(text[len(STUB_PREFIX) + len("toolu_") :].split(" ")[0])
            assert target < i and not sent[target].startswith(STUB_PREFIX)


# -- PR-004, AC-PR-2 --------------------------------------------------------------------------


def test_duplicate_pruning_prefix_stable_across_turns() -> None:
    turn_n = conversation(FILE, OTHER, FILE)
    turn_n1 = conversation(FILE, OTHER, FILE, OTHER)
    _, _, a = run(turn_n)
    _, _, b = run(turn_n1)
    assert b["messages"][: len(a["messages"])] == a["messages"]


def test_duplicate_require_same_call_option() -> None:
    body = conversation(FILE, FILE)
    body["messages"][3]["content"][0]["input"] = {"file_path": "elsewhere.py"}
    _, _, loose = run(body)
    _, _, strict = run(body, require_same_call=True)
    assert results_of(loose)[1] == stub_for("toolu_00", FILE)
    assert results_of(strict)[1] == FILE


# -- PR-005, AC-PR-3 --------------------------------------------------------------------------


def _shape(node: Any) -> Any:
    """The JSON structure with every tool_result content blanked."""
    if isinstance(node, dict):
        return {
            k: ("<result>" if k == "content" and node.get("type") == "tool_result" else _shape(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_shape(v) for v in node]
    return node


@pytest.mark.parametrize("name", sorted(p.stem for p in FIXTURES.glob("*.json")))
def test_pruning_preserves_structure_and_arguments(name: str) -> None:
    body = json.loads((FIXTURES / f"{name}.json").read_bytes())
    _, _, forwarded = run(body, BOTH)
    assert _shape(forwarded) == _shape(body)
    doubled = conversation(FILE, FILE)
    _, _, pruned = run(doubled, BOTH)
    assert _shape(pruned) == _shape(doubled)


# -- PR-010, CC-009, CC-019 -------------------------------------------------------------------


PRETTY = json.dumps({"items": [{"id": i, "name": f"item-{i}"} for i in range(8)]}, indent=2)


def test_pruning_runs_before_segment_compressors() -> None:
    _, result, forwarded = run(conversation(PRETTY, PRETTY, tool="list_items"), BOTH)
    first, second = results_of(forwarded)
    assert second == stub_for("toolu_00", PRETTY)  # stubbed, never minified
    assert first == json.dumps(json.loads(PRETTY), separators=(",", ":"))  # structural: allowed
    chains = {p.segment_id: p.produced_by for p in result.patches}
    assert sorted(chains.values()) == [("duplicate_tool_results",), ("json_minify",)]


class Lossy:
    """A fake LOSSY segment compressor that halves every tool result."""

    spec = dataclasses.replace(
        JSON_SPEC,
        id="zz_lossy",
        kind="LOSSY",
        equivalence="none",
        stage="semantic",
        default_enabled=False,
    )

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability:
        return Applicability(True)

    def compress(self, text: str, view: SegmentView) -> str:
        return text[: len(text) // 2]


def test_reference_target_integrity_enforced() -> None:
    """CC-019 / AC-CC-10: a non-equivalent change to a stub's target is rejected; the stub
    never changes either (its compressor is terminal)."""
    enabled = {"duplicate_tool_results": True, "zz_lossy": True}
    body = conversation(FILE, FILE, OTHER, tool="list_items")
    _, result, forwarded = run(body, enabled, extra=(Lossy(),), verify=False)
    first, second, third = results_of(forwarded)
    assert first == FILE  # the target stays verbatim
    assert second == stub_for("toolu_00", FILE)
    assert third == OTHER[: len(OTHER) // 2]  # not a target: the lossy change is accepted
    lossy = next(s for s in result.stats if s.compressor_id == "zz_lossy")
    assert lossy.rejected_invariant == 1
    assert any(i.reason == "reference_target_modified" for i in result.invocations)


def test_terminal_stops_chain() -> None:
    enabled = {"duplicate_tool_results": True, "zz_lossy": True}
    body = conversation(FILE, FILE, tool="list_items")
    _, result, _ = run(body, enabled, extra=(Lossy(),), verify=False)
    stub = result.patches[-1]
    assert stub.produced_by == ("duplicate_tool_results",)
    skipped = [
        i
        for i in result.invocations
        if i.compressor_id == "zz_lossy" and i.segment_id == stub.segment_id
    ]
    assert [i.reason for i in skipped] == ["after_terminal"]


def test_chain_order_by_stage_then_id() -> None:
    engine = Engine((Lossy(), *REGISTRY), EngineSettings(enabled={}, verbatim_tools=frozenset()))
    assert [c.spec.id for c in engine.compressors] == [
        "json_minify",
        "duplicate_tool_results",
        "zz_lossy",
    ]


# -- PR-011, PR-013, PR-015 -------------------------------------------------------------------


def test_stub_preserves_cache_control_and_is_error() -> None:
    body = conversation(
        FILE, {"content": FILE, "is_error": True, "cache_control": {"type": "ephemeral"}}
    )
    _, _, forwarded = run(body)
    block = forwarded["messages"][4]["content"][0]
    assert block["content"] == stub_for("toolu_00", FILE)
    assert block["is_error"] is True and block["cache_control"] == {"type": "ephemeral"}


def test_duplicate_pruning_applies_to_verbatim_tools() -> None:
    """CC-021 / AC-CC-12 / AC-PR-9: `Read` is a verbatim tool; json_minify skips it, the
    reference pruner does not."""
    _, result, forwarded = run(conversation(PRETTY, PRETTY, tool="Read"), BOTH)
    assert results_of(forwarded) == [PRETTY, stub_for("toolu_00", PRETTY)]
    minify = next(s for s in result.stats if s.compressor_id == "json_minify")
    assert minify.skip_reasons.get("verbatim_tool", 0) >= 1


def test_duplicate_stub_keeps_protected_spans() -> None:
    with_reminder = FILE + REMINDER
    _, result, forwarded = run(conversation(with_reminder, with_reminder))
    assert results_of(forwarded)[1] == stub_for("toolu_00", with_reminder) + "\n" + REMINDER
    assert result.reference_stubs == 1


def test_multi_block_results_not_pruned() -> None:
    blocks = [{"type": "text", "text": FILE}, {"type": "text", "text": OTHER}]
    single = conversation(blocks, FILE, blocks)
    _, result, forwarded = run(single)
    assert results_of(forwarded) == [blocks, FILE, blocks] and result.reference_stubs == 0
    as_list = conversation(FILE, [{"type": "text", "text": FILE}])  # one text block = whole result
    _, _, pruned = run(as_list)
    assert results_of(pruned)[1] == [{"type": "text", "text": stub_for("toolu_00", FILE)}]


def test_reference_stubs_counted() -> None:
    _, result, _ = run(conversation(FILE, FILE, OTHER, OTHER, FILE))
    assert result.reference_stubs == 3


# -- CC-002 after S4 SCR-001, TC-003 ------------------------------------------------------------


def test_non_lossless_compressors_run_only_when_enabled() -> None:
    """AC-CC-1: kinds never gate; enabling does. Disabled fakes are never called."""
    lossy = Lossy()
    body = conversation(OTHER, tool="list_items")
    _, off, _ = run(body, {}, extra=(lossy,), verify=False)
    assert off.patches == ()
    _, _, forwarded = run(body, {"zz_lossy": True}, extra=(lossy,), verify=False)
    assert results_of(forwarded) == [OTHER[: len(OTHER) // 2]]


def test_policy_field_derived_from_enabled_kinds() -> None:
    lossless = Engine(REGISTRY, EngineSettings(enabled=BOTH, verbatim_tools=frozenset()))
    assert lossless.policy == "LOSSLESS_ONLY"
    mixed = Engine(
        (*REGISTRY, Lossy()),
        EngineSettings(enabled={**BOTH, "zz_lossy": True}, verbatim_tools=frozenset()),
    )
    assert mixed.policy == "LOSSY_ALLOWED"
    off = Engine((*REGISTRY, Lossy()), EngineSettings(enabled=BOTH, verbatim_tools=frozenset()))
    assert off.policy == "LOSSLESS_ONLY"


@settings(max_examples=80, deadline=None)
@given(st.lists(st.sampled_from([*POOL, PRETTY]), min_size=1, max_size=8))
def prop_marginal_savings_sum_to_total_with_pruning(texts: list[str]) -> None:
    _, result, _ = run(conversation(*texts, tool="list_items"), BOTH)
    assert sum(s.marginal_saved for s in result.stats) == (
        result.est_original_tokens - result.est_forwarded_tokens
    )


def test_pruner_records_why_it_did_not_stub() -> None:
    """Dogfood 2026-10-03: the pruner considered 12 results and stubbed none, and the trace
    could not say why. Each result it leaves alone now carries a compressor-specific reason
    (TOKLI_OBSERVABILITY §4: `not_applicable(<short code>)`), metadata only."""
    blocks = [{"type": "text", "text": FILE}, {"type": "text", "text": REMINDER}]
    body = conversation(FILE, blocks, "tiny", "tiny", FILE)
    body["messages"][-2]["content"][0]["input"] = {"file_path": "other.py"}
    body["messages"][7]["content"][0]["input"] = {"file_path": "f2.py"}  # same call as "tiny" 1
    _, result, _ = run(body, require_same_call=True)
    reasons = next(
        s for s in result.stats if s.compressor_id == "duplicate_tool_results"
    ).skip_reasons
    assert reasons == {
        "not_applicable(no_earlier_copy)": 2,  # the first FILE and the first "tiny"
        "not_applicable(multi_block)": 2,  # the two blocks of the multi-block result
        "not_applicable(small_duplicate)": 1,  # the second "tiny": below duplicate_min_tokens
        "not_applicable(not_same_call)": 1,  # FILE again, but from a call with other arguments
    }
