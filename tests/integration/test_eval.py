"""SPEC 012 smoke tier end to end against a fake upstream: QE-001, QE-005, QE-009…QE-012,
QE-014, QE-017…QE-019. No provider is ever called."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from tests.conftest import Cli
from tests.integration.servers import BYTE_CATALOG, FakeUpstream, make_config, provision
from tokli.app.bootstrap import Services, bootstrap
from tokli.compression.contract import Applicability, SegmentView
from tokli.compression.engine import Engine, EngineSettings
from tokli.compression.stages import CompressionStage, FeaturesStage
from tokli.compressors.json_minify import SPEC as JSON_SPEC
from tokli.domain.stage import Features
from tokli.eval.cases import load_cases
from tokli.eval.runner import Arm, plan_run, run_smoke
from tokli.eval.verdict import family_verdict, overall_verdict
from tokli.pipeline.pipeline import Pipeline
from tokli.pipeline.reminders import RemindersStage

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evals" / "cases"
KEY = "sk-ant-api03-TOKLI-CANARY-EVAL-KEY"
ASSUMPTIONS = JSON_SPEC.assumptions


# -- a fake model that "reads" the forwarded tool result -----------------------------------------


def _tool_result_and_question(body: dict[str, Any]) -> tuple[str, str]:
    content = body["messages"][-1]["content"]
    result = next(b["content"] for b in content if b.get("type") == "tool_result")
    question = next(b["text"] for b in content if b.get("type") == "text")
    return result, question


def oracle_upstream(upstream: FakeUpstream, seen: list[dict[str, Any]] | None = None) -> None:
    """Answers correctly only when the expected answer can be read from the forwarded tool
    result; so a compressor that damages the result makes the candidate arm fail."""
    expected = {}
    for case in load_cases(CASES, ASSUMPTIONS):
        _, question = _tool_result_and_question(case.request)
        expected[question] = (case.checker, case.expected)

    async def responder(request: Request) -> Response:
        body = json.loads(await request.body())
        if seen is not None:
            seen.append({"headers": dict(request.headers), "body": body})
        result, question = _tool_result_and_question(body)
        checker, answer = expected[question]
        if checker == "exact_value":
            text = answer if answer in result else "unknown"
        else:
            try:
                items = json.loads(result)["items"]
            except (ValueError, KeyError, TypeError):
                items = []
            text = answer if json.loads(answer) in items else "{}"
        return JSONResponse(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": len(result) // 4 + 50, "output_tokens": 20},
            }
        )

    upstream.responder = responder


# -- arms -----------------------------------------------------------------------------------


class DropDigits:
    """A destructive fake compressor (AC-QE-2): drops every digit of JSON tool results."""

    spec = dataclasses.replace(JSON_SPEC, id="drop_digits", kind="LOSSLESS")

    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability:
        return Applicability(features.json_candidate, "" if features.json_candidate else "no")

    def compress(self, text: str, view: SegmentView) -> str:
        return "".join(ch for ch in text if not ch.isdigit())


class Identity(DropDigits):
    """Identity on content (QE-017): re-indents the JSON with one space instead of two. A
    byte-identical output would leave every case `not_exercised` (QE-012), so the harmless
    transformation must change bytes while keeping every value."""

    spec = dataclasses.replace(JSON_SPEC, id="identity", kind="LOSSLESS")

    def compress(self, text: str, view: SegmentView) -> str:
        return json.dumps(json.loads(text), indent=1)


def services_with(base: Services, compressor: Any | None) -> Services:
    settings = EngineSettings(
        enabled={compressor.spec.id: True} if compressor else {},
        verbatim_tools=frozenset({"Read", "Bash"}),
        min_gain_tokens=0,
        min_gain_ratio=0.0,
    )
    engine = Engine([compressor] if compressor else [], settings)
    pipeline = Pipeline(
        [RemindersStage(), FeaturesStage(base.selector), CompressionStage(engine, base.selector)]
    )
    return dataclasses.replace(base, pipeline=pipeline)


def real_arms(tmp_path: Path, url: str) -> tuple[Arm, Arm]:
    """The arms the CLI builds: every compressor off vs only json_minify on (QE-012)."""
    off = make_config(tmp_path / "off", url, "compressors.json_minify.enabled=false")
    on = make_config(tmp_path / "on", url, "compressors.json_minify.enabled=true")
    return (
        Arm("baseline", bootstrap(off, catalog=BYTE_CATALOG, version="test", telemetry=False)),
        Arm("candidate", bootstrap(on, catalog=BYTE_CATALOG, version="test", telemetry=False)),
    )


def run(arms: tuple[Arm, Arm], *, max_calls: int = 10_000, repetitions: int = 1):  # type: ignore[no-untyped-def]
    cases = load_cases(CASES, ASSUMPTIONS)
    plan = plan_run(cases, arms, repetitions=repetitions, model="claude-test")
    return plan, asyncio.run(run_smoke(plan, arms, api_key=KEY, max_calls=max_calls))


def by_family(result) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    families: dict[str, list[Any]] = {}
    for case in result.cases:
        families.setdefault(case.family, []).append(case)
    return {name: family_verdict(items) for name, items in families.items()}


# S8a-1 added families for `not_quoted_verbatim` whose content json_minify never changes; after
# S8a SCR-002 they are reported `not_exercised` and stay out of the verdict.
UNEXERCISED_FOR_JSON = {"grep_verbatim_quote", "log_verbatim_quote"}


def judged(result) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """The families with at least one exercised case; asserts that the others are exactly the
    families json_minify cannot change."""
    families = by_family(result)
    idle = {name for name, v in families.items() if v.verdict == "not_exercised"}
    assert idle == UNEXERCISED_FOR_JSON, idle
    return {name: v for name, v in families.items() if name not in idle}


# -- tests ----------------------------------------------------------------------------------


def test_smoke_harness_self_test(tmp_path: Path, upstream: FakeUpstream) -> None:
    """QE-017: identity → no measurable damage; a digit-dropping compressor → damage."""
    oracle_upstream(upstream)
    base = bootstrap(
        make_config(tmp_path, upstream.url), catalog=BYTE_CATALOG, version="t", telemetry=False
    )
    baseline = Arm("baseline", services_with(base, None))
    for compressor, expected in (
        (Identity(), "no_measurable_damage"),
        (DropDigits(), "damage_detected"),
    ):
        candidate = Arm("candidate", services_with(base, compressor))
        _, result = run((baseline, candidate))
        families = judged(result)
        verdicts = {v.verdict for v in families.values()}
        if expected == "damage_detected":
            assert "damage_detected" in verdicts, (compressor.spec.id, verdicts)
        else:
            assert verdicts == {"no_measurable_damage"}, verdicts
        assert overall_verdict(list(by_family(result).values()), ASSUMPTIONS) == expected


def test_harness_uses_real_pipeline(tmp_path: Path, upstream: FakeUpstream) -> None:
    """QE-001 / QE-012: json_minify through the real bootstrap and pipeline; real cases pass."""
    seen: list[dict[str, Any]] = []
    oracle_upstream(upstream, seen)
    plan, result = run(real_arms(tmp_path, upstream.url))
    exercised = len(plan.cases) - plan.not_exercised
    assert plan.not_exercised == 44  # grep_verbatim_quote and log_verbatim_quote: no JSON
    assert result.calls == plan.calls == 2 * exercised  # unexercised cases make no call
    verdicts = judged(result)
    assert {v.verdict for v in verdicts.values()} == {"no_measurable_damage"}
    assert all(v.n >= 20 for v in verdicts.values())
    minified = [s for s in seen if "\n  " not in _tool_result_and_question(s["body"])[0]]
    assert len(minified) == exercised  # the candidate arm's bodies were minified
    for sent in seen:
        assert sent["body"]["model"] == "claude-test"
        assert sent["body"]["temperature"] == 0 and sent["body"]["stream"] is False


def test_smoke_arms_differ_only_in_candidate(tmp_path: Path, upstream: FakeUpstream) -> None:
    oracle_upstream(upstream)
    baseline, candidate = real_arms(tmp_path, upstream.url)
    case = next(c for c in load_cases(CASES, ASSUMPTIONS) if c.family.startswith("json_"))
    body = json.dumps({**case.request, "model": "m", "temperature": 0, "stream": False}).encode()
    base, cand = baseline.prepare(body), candidate.prepare(body)
    assert base.body == body  # every compressor off: the request is forwarded as built
    assert cand.body != body
    a, b = json.loads(base.body), json.loads(cand.body)
    a["messages"][-1]["content"][0]["content"] = b["messages"][-1]["content"][0]["content"] = ""
    assert a == b  # only the tool result differs
    assert cand.ms_compressor >= 0 and base.est_tokens > cand.est_tokens


def test_eval_stops_at_call_cap(tmp_path: Path, upstream: FakeUpstream) -> None:
    """QE-010 / QE-018: no call beyond the cap; unfinished cases give insufficient data."""
    seen: list[dict[str, Any]] = []
    oracle_upstream(upstream, seen)
    _, result = run(real_arms(tmp_path, upstream.url), max_calls=10)
    assert len(seen) == 10 and result.calls == 10 and result.stopped_by_cap
    assert {v.verdict for v in judged(result).values()} == {"insufficient_data"}


def test_eval_sends_key_only_as_header(tmp_path: Path, upstream: FakeUpstream) -> None:
    seen: list[dict[str, Any]] = []
    oracle_upstream(upstream, seen)
    run(real_arms(tmp_path, upstream.url), max_calls=2)
    assert len(seen) == 2
    assert all(s["headers"]["x-api-key"] == KEY for s in seen)
    assert all(s["headers"]["anthropic-version"] for s in seen)


# -- the CLI ----------------------------------------------------------------------------------


@pytest.fixture
def eval_cli(cli: Cli, upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    from tokli.app import bootstrap as bootstrap_module

    real = bootstrap_module.bootstrap
    monkeypatch.setattr(
        "tokli.cli.main.bootstrap",
        lambda config, **kw: real(config, catalog=BYTE_CATALOG, version="test", **kw),
    )
    data_dir = cli.workdir / "data"
    provision(data_dir)
    evals = tmp_path / "evals"
    (evals / "records").mkdir(parents=True)
    shutil.copytree(CASES, evals / "cases")
    oracle_upstream(upstream)

    def run_cli(*extra: str, env: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
        for name, value in (env or {"EVAL_TEST_ANTHROPIC_KEY": KEY}).items():
            monkeypatch.setenv(name, value)
        return cli.run(
            "eval",
            "smoke",
            "--compressor",
            "json_minify",
            "--model",
            "claude-test",
            "--evals-dir",
            str(evals),
            "--data-dir",
            str(data_dir),
            "--set",
            f"upstreams.anthropic.base_url={upstream.url}",
            "--repetitions",
            "1",
            *extra,
        )

    return run_cli, evals


def test_eval_requires_max_calls_without_pricing(eval_cli, upstream: FakeUpstream) -> None:  # type: ignore[no-untyped-def]
    run_cli, _ = eval_cli
    result = run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", "--yes")
    assert result.code != 0 and "--max-calls" in result.err
    assert upstream.received == []


def test_eval_requires_confirmation_or_yes(
    eval_cli, upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """QE-009 / QE-018: the plan is shown; a declined prompt makes no call."""
    run_cli, _ = eval_cli
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    result = run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", "--max-calls", "200")
    assert "88 calls" in result.out and "estimated input tokens" in result.out
    assert result.code != 0 and upstream.received == []

    def no_terminal(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_terminal)
    assert run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", "--max-calls", "200").code != 0
    assert upstream.received == []


def test_eval_api_key_from_named_env_only(eval_cli, upstream: FakeUpstream) -> None:  # type: ignore[no-untyped-def]
    """QE-019: ANTHROPIC_API_KEY in the environment is not used unless named."""
    run_cli, _ = eval_cli
    result = run_cli(
        "--api-key-env",
        "EVAL_TEST_MISSING_KEY",
        "--max-calls",
        "200",
        "--yes",
        env={"ANTHROPIC_API_KEY": KEY},
    )
    assert result.code != 0 and "EVAL_TEST_MISSING_KEY" in result.err
    assert KEY not in result.err + result.out
    assert upstream.received == []


def test_harness_report_provenance(eval_cli) -> None:  # type: ignore[no-untyped-def]
    """QE-005 / QE-014 / QE-016: report, record and per-case results are written."""
    run_cli, evals = eval_cli
    result = run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", "--max-calls", "200", "--yes")
    assert result.code == 0, result.err
    record = yaml.safe_load((evals / "records" / "json_minify.yaml").read_text(encoding="utf-8"))
    assert record["tier"] == "smoke" and record["verdict"] == "no_measurable_damage"
    assert record["version"] == JSON_SPEC.version and record["model"] == "claude-test"
    assert set(record["assumptions_covered"]) == set(ASSUMPTIONS)
    report = evals / record["report"]
    text = report.read_text(encoding="utf-8")
    for field in (
        "Tokli version",
        "config_hash",
        "baseline",
        "candidate",
        "case set",
        "repetitions",
        "json_minify",
        "claude-test",
        "only gross damage",
        "forwarded input tokens",
        "exact",
        "ms",
    ):
        assert field in text, field
    lines = (report.parent / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert {"case_id", "arm", "repetition", "outcome", "input_tokens", "answer"} <= set(first)
    assert len(lines) == 88
    assert "progress: 10/88 calls" in result.out and "progress: 88/88 calls" in result.out


def test_eval_never_writes_the_key(eval_cli) -> None:  # type: ignore[no-untyped-def]
    run_cli, evals = eval_cli
    result = run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", "--max-calls", "200", "--yes")
    assert result.code == 0
    outputs = [*(evals / "records").rglob("*"), *(evals / "results").rglob("*")]
    written = "".join(p.read_text(encoding="utf-8") for p in outputs if p.is_file())
    assert written
    assert "TOKLI-CANARY-EVAL" not in written + result.out + result.err


def test_eval_never_auto_starts() -> None:
    """QE-011: nothing on the proxy path or at startup reaches the eval package."""
    import importlib
    import sys

    for name in [m for m in sys.modules if m.startswith("tokli.eval")]:
        del sys.modules[name]
    importlib.import_module("tokli.http.app")
    importlib.import_module("tokli.app.bootstrap")
    assert not any(m.startswith("tokli.eval") for m in sys.modules)


def test_eval_reports_provider_errors_and_stops_early(eval_cli, upstream: FakeUpstream) -> None:  # type: ignore[no-untyped-def]
    """Regression (found in the first real smoke run, 2026-10-03): all 264 calls were answered
    400 and the run gave no hint why. Root cause: the runner kept only the answer text, so the
    provider's error type and message were lost, and it kept calling after every call failed.
    Now the error type and message are recorded and shown, and 10 consecutive errors stop it."""

    async def rejecting(request: Request) -> Response:
        return JSONResponse(
            {
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "a synthetic rejection"},
            },
            status_code=400,
        )

    upstream.responder = rejecting
    run_cli, evals = eval_cli
    result = run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", "--max-calls", "200", "--yes")
    assert result.code == 0, result.err
    assert len(upstream.received) == 10  # stopped after 10 consecutive errors
    assert "insufficient_data" in result.out
    assert "10 consecutive errors" in result.out
    assert "invalid_request_error" in result.out and "a synthetic rejection" in result.out
    record = yaml.safe_load((evals / "records" / "json_minify.yaml").read_text(encoding="utf-8"))
    assert record["verdict"] == "insufficient_data"
    rows = (evals / record["report"]).parent.joinpath("cases.jsonl").read_text(encoding="utf-8")
    first = json.loads(rows.splitlines()[0])
    assert first["error"] == {"type": "invalid_request_error", "message": "a synthetic rejection"}
    report = (evals / record["report"]).read_text(encoding="utf-8")
    assert "invalid_request_error" in report


def test_eval_temperature_default_omits_the_parameter(eval_cli, upstream: FakeUpstream) -> None:  # type: ignore[no-untyped-def]
    """S2.5 SCR-001: some models reject `temperature`; `--temperature default` sends none, in
    both arms, and the report says so."""
    run_cli, evals = eval_cli
    result = run_cli(
        "--api-key-env",
        "EVAL_TEST_ANTHROPIC_KEY",
        "--max-calls",
        "200",
        "--yes",
        "--temperature",
        "default",
    )
    assert result.code == 0, result.err
    bodies = [json.loads(r.body) for r in upstream.received]
    assert len(bodies) == 88 and all("temperature" not in b for b in bodies)
    record = yaml.safe_load((evals / "records" / "json_minify.yaml").read_text(encoding="utf-8"))
    report = (evals / record["report"]).read_text(encoding="utf-8")
    assert "| Temperature | model default |" in report


def test_eval_temperature_zero_by_default(eval_cli, upstream: FakeUpstream) -> None:  # type: ignore[no-untyped-def]
    run_cli, evals = eval_cli
    assert (
        run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", "--max-calls", "4", "--yes").code == 0
    )
    assert all(json.loads(r.body)["temperature"] == 0 for r in upstream.received)
    record = yaml.safe_load((evals / "records" / "json_minify.yaml").read_text(encoding="utf-8"))
    assert "| Temperature | 0 |" in (evals / record["report"]).read_text(encoding="utf-8")


# -- S4: the reference families (E11) -----------------------------------------------------------


from tokli.compression.contract import Proposal  # noqa: E402
from tokli.compressors.duplicate_tool_results import SPEC as DUP_SPEC  # noqa: E402

REF_ASSUMPTIONS = DUP_SPEC.assumptions


def all_results(body: dict[str, Any]) -> str:
    return "\n".join(
        block["content"] if isinstance(block["content"], str) else json.dumps(block["content"])
        for message in body["messages"]
        if message["role"] == "user" and isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    )


def reference_oracle(upstream: FakeUpstream) -> None:
    """Answers correctly only when the answer is still somewhere in the forwarded tool results."""
    expected = {}
    for case in load_cases(CASES, REF_ASSUMPTIONS):
        if not case.family.startswith("reference_"):  # the E11 families only
            continue
        question = case.request["messages"][-1]["content"][-1]["text"]
        expected[question] = case.expected

    async def responder(request: Request) -> Response:
        body = json.loads(await request.body())
        question = body["messages"][-1]["content"][-1]["text"]
        answer = expected[question]
        text = answer if answer in all_results(body) else "I cannot find it."
        return JSONResponse(
            {
                "type": "message",
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 9},
            }
        )

    upstream.responder = responder


class StubEverything:
    """A destructive fake request compressor: replaces every whole tool result, including the
    first copy, so the information is gone."""

    spec = dataclasses.replace(DUP_SPEC, id="stub_everything", kind="LOSSY", equivalence="none")

    def plan(self, refs, texts, tools, count, conversation=None):  # type: ignore[no-untyped-def]
        return [Proposal(r.segment_id, "[omitted]") for r in refs if r.whole_result]

    def decode_request(self, texts, refs):  # type: ignore[no-untyped-def]
        return {}


def test_smoke_harness_self_test_reference_families(tmp_path: Path, upstream: FakeUpstream) -> None:
    """QE-017 for E11: the real pruner keeps the answer in the request (no damage); a pruner
    that drops the first copy too is detected."""
    reference_oracle(upstream)
    off = make_config(
        tmp_path / "off",
        upstream.url,
        "compressors.json_minify.enabled=false",
        "compressors.duplicate_tool_results.enabled=false",
    )
    on = make_config(
        tmp_path / "on",
        upstream.url,
        "compressors.json_minify.enabled=false",
        "compressors.duplicate_tool_results.enabled=true",
    )
    baseline = Arm("baseline", bootstrap(off, catalog=BYTE_CATALOG, version="t", telemetry=False))
    candidate = Arm("candidate", bootstrap(on, catalog=BYTE_CATALOG, version="t", telemetry=False))
    cases = [c for c in load_cases(CASES, REF_ASSUMPTIONS) if c.family.startswith("reference_")]
    plan = plan_run(cases, (baseline, candidate), repetitions=1, model="claude-test")
    assert plan.not_exercised == 0  # every case has a later identical read to stub
    result = asyncio.run(run_smoke(plan, (baseline, candidate), api_key=KEY, max_calls=10_000))
    assert {v.verdict for v in by_family(result).values()} == {"no_measurable_damage"}

    engine_settings = EngineSettings(
        enabled={"stub_everything": True},
        verbatim_tools=frozenset(),
        min_gain_tokens=0,
        min_gain_ratio=0.0,
    )
    pipeline = Pipeline(
        [
            RemindersStage(),
            FeaturesStage(baseline.services.selector),
            CompressionStage(
                Engine([StubEverything()], engine_settings), baseline.services.selector
            ),
        ]
    )
    destructive = Arm("candidate", dataclasses.replace(baseline.services, pipeline=pipeline))
    plan = plan_run(cases, (baseline, destructive), repetitions=1, model="claude-test")
    result = asyncio.run(run_smoke(plan, (baseline, destructive), api_key=KEY, max_calls=10_000))
    assert {v.verdict for v in by_family(result).values()} == {"damage_detected"}


# -- S8c: a read of the right file passes `answer_or_read` -----------------------------------------


def test_answer_or_read_counts_a_read_call(tmp_path: Path, upstream: FakeUpstream) -> None:
    """QE-020 `answer_or_read` through the runner: a response that only calls `Read` on the
    case's file is a pass, not an empty answer."""
    cases = load_cases(CASES, ("edit_content_not_needed",))
    paths = {c.request["messages"][-1]["content"]: c.expected_read_path for c in cases}

    async def responder(request: Request) -> Response:
        body = json.loads(await request.body())
        path = paths[body["messages"][-1]["content"]]
        return JSONResponse(
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_r",
                        "name": "Read",
                        "input": {"file_path": path},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 100, "output_tokens": 10},
            }
        )

    upstream.responder = responder
    off = make_config(
        tmp_path / "off",
        upstream.url,
        "compressors.json_minify.enabled=false",
        "compressors.duplicate_tool_results.enabled=false",
    )
    on = make_config(
        tmp_path / "on",
        upstream.url,
        "compressors.json_minify.enabled=false",
        "compressors.duplicate_tool_results.enabled=false",
        "compressors.edit_args_on_resume.enabled=true",
    )
    baseline = Arm("baseline", bootstrap(off, catalog=BYTE_CATALOG, version="t", telemetry=False))
    candidate = Arm("candidate", bootstrap(on, catalog=BYTE_CATALOG, version="t", telemetry=False))
    plan = plan_run(cases, (baseline, candidate), repetitions=1, model="claude-test")
    assert plan.not_exercised == 0
    result = asyncio.run(run_smoke(plan, (baseline, candidate), api_key=KEY, max_calls=10_000))
    assert {v.verdict for v in by_family(result).values()} == {"no_measurable_damage"}
    assert all(set(c.candidate) == {"pass"} for c in result.cases)


# -- S8e: an exact `Edit` passes `edit_anchor` through the runner ---------------------------------


def test_edit_anchor_counts_an_exact_edit(tmp_path: Path, upstream: FakeUpstream) -> None:
    """QE-020 `edit_anchor` through the runner: a response that edits the marker line with an
    exact anchor is a pass."""
    cases = load_cases(CASES, ("quotes_from_reference_target",))
    cases = [c for c in cases if c.family == "reread_edit_anchor"]
    assert len(cases) == 22
    by_question = {c.request["messages"][-1]["content"]: c for c in cases}

    async def responder(request: Request) -> Response:
        body = json.loads(await request.body())
        case = by_question[body["messages"][-1]["content"]]
        edit = {
            "file_path": case.expected_read_path,
            "old_string": case.expected,
            "new_string": "x",
        }
        return JSONResponse(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_e", "name": "Edit", "input": edit}],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 100, "output_tokens": 10},
            }
        )

    upstream.responder = responder
    base = (
        "compressors.json_minify.enabled=false",
        "compressors.duplicate_tool_results.enabled=false",
    )
    # The baseline arm has every compressor off (QE-012); this pruner is on by default since S8e.
    off = make_config(
        tmp_path / "off", upstream.url, *base, "compressors.reread_by_reference.enabled=false"
    )
    on = make_config(
        tmp_path / "on", upstream.url, *base, "compressors.reread_by_reference.enabled=true"
    )
    baseline = Arm("baseline", bootstrap(off, catalog=BYTE_CATALOG, version="t", telemetry=False))
    candidate = Arm("candidate", bootstrap(on, catalog=BYTE_CATALOG, version="t", telemetry=False))
    plan = plan_run(cases, (baseline, candidate), repetitions=1, model="claude-test")
    assert plan.not_exercised == 0
    result = asyncio.run(run_smoke(plan, (baseline, candidate), api_key=KEY, max_calls=10_000))
    assert all(set(c.candidate) == {"pass"} and set(c.baseline) == {"pass"} for c in result.cases)


PRICED = ("--model", "claude-haiku-4-5")


def test_eval_requires_confirmation_or_max_cost(
    eval_cli, upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """QE-009 (S6): for a priced model the plan shows the estimated cost; `--yes` alone is not
    enough without a cap, and a declined prompt makes no call."""
    run_cli, _ = eval_cli
    result = run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", *PRICED, "--yes")
    assert result.code != 0 and "--max-cost" in result.err
    assert upstream.received == []
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    result = run_cli("--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", *PRICED)
    assert "estimated cost: at most $" in result.out
    assert result.code != 0 and upstream.received == []


def test_eval_stops_at_cost_cap(eval_cli, upstream: FakeUpstream) -> None:  # type: ignore[no-untyped-def]
    """QE-010: the run stops before the call that would exceed `--max-cost`, counting the cost
    from provider usage, and says so."""
    run_cli, _ = eval_cli
    result = run_cli(
        "--api-key-env", "EVAL_TEST_ANTHROPIC_KEY", *PRICED, "--max-cost", "0.01", "--yes"
    )
    assert result.code == 0, result.err
    assert 0 < len(upstream.received) < 88
    assert "stopped by the cost cap" in result.out
