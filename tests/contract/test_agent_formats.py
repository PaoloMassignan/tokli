"""Every compressor acts on the real shapes of agent traffic (S8h P2; TOKLI_TEST_STRATEGY §2).

`tests/fixtures/agent_formats/claude_code.json` holds synthetic content in the shapes measured on
real Claude Code sessions (see `make_claude_code.py`). A compressor whose assumptions about the
agent's output are wrong fails here, instead of passing synthetic tests in a format the agent
never sends (S8h SCR-001: `reread_by_reference` and Claude Code's `Read` numbering).

Every registered compressor needs an entry in EXPECTATIONS; a new compressor without one fails
`test_every_compressor_has_a_real_format_expectation`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.helpers import FakeCounter
from tokli.compression.engine import Engine, EngineResult, EngineSettings
from tokli.compression.registry import REGISTRY
from tokli.compression.stages import CompressionStage, FeaturesStage
from tokli.config.schema import TokliSettings
from tokli.domain.models import SegmentKind
from tokli.domain.stage import StageContext
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage
from tokli.protocols.anthropic_messages import parse

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_formats" / "claude_code.json"
DEFAULTS = TokliSettings()


class Selector:
    def select(self, model: str | None) -> FakeCounter:
        return FakeCounter()


def run_alone(cid: str, *, opt_in: bool = False) -> EngineResult:
    """The fixture through the real pipeline with only ``cid`` enabled and default settings."""
    body = FIXTURE.read_bytes()
    request = parse(
        body,
        mutable_kinds=frozenset({SegmentKind.TOOL_RESULT, SegmentKind.USER_TEXT}),
    )
    engine = Engine(
        REGISTRY,
        EngineSettings(
            enabled={cid: True},
            verbatim_tools=frozenset(DEFAULTS.compression.verbatim_tools),
            verbatim_opt_in=frozenset({cid}) if opt_in else frozenset(),
            request_budget_ms=1e9,  # about formats, not time
        ),
    )
    pipeline = Pipeline(
        [RemindersStage(), FeaturesStage(Selector()), CompressionStage(engine, Selector())]
    )
    report = pipeline.run(request, StageContext(request_id="formats")).reports[
        "transform.compression"
    ]
    assert isinstance(report, EngineResult)
    return report


def accepted(report: EngineResult, cid: str) -> int:
    return next(s.accepted for s in report.stats if s.compressor_id == cid)


def tool_inputs(name: str) -> list[dict[str, object]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        block["input"]
        for message in data["messages"]
        if isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_use" and block.get("name") == name
    ]


def expect_json_minify() -> None:
    assert accepted(run_alone("json_minify"), "json_minify") >= 1  # MCP text-block JSON


def expect_duplicate_tool_results() -> None:
    assert accepted(run_alone("duplicate_tool_results"), "duplicate_tool_results") >= 1


def expect_reread_by_reference() -> None:
    # a re-read after an Edit and a read of a just-written file, both in Claude Code's numbering
    assert accepted(run_alone("reread_by_reference"), "reread_by_reference") == 2


def expect_search_group() -> None:
    assert accepted(run_alone("search_group"), "search_group") >= 1  # the Grep tool's lines


def expect_log_filter() -> None:
    # Bash is a verbatim tool, so log_filter acts on it only with its opt-in (CC-021 b)
    assert accepted(run_alone("log_filter", opt_in=True), "log_filter") >= 1


def expect_edit_args_on_resume() -> None:
    """Its assumption about the agent's output is the argument names of the edit tools: every
    configured field must exist in the real shape of that tool's input (MultiEdit does not
    occur in the measured traffic and is not checked)."""
    for tool, fields in DEFAULTS.pruning.resume_edit_fields.items():
        inputs = tool_inputs(tool)
        if tool == "MultiEdit":
            continue
        assert inputs, f"no {tool} call in the fixture"
        for field in fields:
            assert all(field in args for args in inputs), (tool, field)


EXPECTATIONS: dict[str, Callable[[], None]] = {
    "json_minify": expect_json_minify,
    "duplicate_tool_results": expect_duplicate_tool_results,
    "reread_by_reference": expect_reread_by_reference,
    "search_group": expect_search_group,
    "log_filter": expect_log_filter,
    "edit_args_on_resume": expect_edit_args_on_resume,
}


def test_every_compressor_has_a_real_format_expectation() -> None:
    assert set(EXPECTATIONS) == {c.spec.id for c in REGISTRY}


@pytest.mark.parametrize("cid", sorted(EXPECTATIONS))
def test_compressor_acts_on_real_agent_formats(cid: str) -> None:
    EXPECTATIONS[cid]()
