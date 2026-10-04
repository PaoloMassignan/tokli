"""Smoke runner (QE-001, QE-010, QE-012, QE-014, QE-018, QE-019).

Each arm is a full service set built by the same bootstrap as ``tokli serve``; a case's body goes
through the real parse → pipeline → render and is sent by the proxy's upstream client. Nothing
here touches the proxy's request path or its telemetry.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from tokli.app.api import compression_report
from tokli.app.bootstrap import Services
from tokli.domain.stage import StageContext
from tokli.eval.cases import Case
from tokli.eval.checkers import CHECKERS, TOOL_CHECKERS, ToolCall
from tokli.eval.record import ArmTotals
from tokli.eval.verdict import CaseResult
from tokli.protocols.anthropic_messages import estimate_request_tokens, parse, render
from tokli.protocols.anthropic_usage import BodyUsageParser
from tokli.upstream.forwarder import UpstreamError

ANTHROPIC_VERSION = "2023-06-01"
_RESPONSE_LIMIT = 4 * 1024 * 1024
_ANSWER_LIMIT = 4000
_MESSAGE_LIMIT = 300
MAX_CONSECUTIVE_ERRORS = 10  # every call failing means the run cannot judge anything


@dataclass(frozen=True)
class Prepared:
    body: bytes
    est_tokens: int
    ms_compressor: float


class Arm:
    """One side of the comparison: a service set and its name (``baseline``/``candidate``)."""

    def __init__(self, name: str, services: Services) -> None:
        self.name = name
        self.services = services

    def prepare(self, body: bytes) -> Prepared:
        services = self.services
        request = parse(body, mutable_kinds=services.mutable_kinds, arg_fields=services.arg_fields)
        counter = services.selector.select(request.model)
        result = services.pipeline.run(request, StageContext(request_id=f"eval-{self.name}"))
        report = compression_report(result.reports)
        ms = sum(s.ms_total for s in report.stats) if report is not None else 0.0
        forwarded = render(request, result.patches) if result.patches else body
        estimate = estimate_request_tokens(
            parse(forwarded, mutable_kinds=services.mutable_kinds, arg_fields=services.arg_fields),
            counter.count,
        )
        return Prepared(forwarded, estimate, ms)


@dataclass(frozen=True)
class PlannedCase:
    case: Case
    prepared: dict[str, Prepared]

    @property
    def not_exercised(self) -> bool:
        bodies = {p.body for p in self.prepared.values()}
        return len(bodies) == 1  # the candidate forwards exactly what the baseline forwards


@dataclass
class Plan:
    cases: list[PlannedCase]
    repetitions: int
    model: str
    calls: int
    est_input_tokens: int

    @property
    def not_exercised(self) -> int:
        return sum(1 for c in self.cases if c.not_exercised)


@dataclass
class RunResult:
    cases: list[CaseResult] = field(default_factory=list)
    calls: int = 0
    stopped_by_cap: bool = False
    stopped_by_errors: bool = False
    errors: dict[tuple[str, str], int] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, ArmTotals] = field(default_factory=dict)


def request_body(case: Case, model: str, temperature: str = "0") -> bytes:
    """The case's body for ``model``. ``temperature`` is "0", or "default" to send none (some
    models reject the parameter; S2.5 SCR-001)."""
    body: dict[str, Any] = {**case.request, "model": model, "stream": False}
    if temperature != "default":
        body["temperature"] = int(temperature)
    return json.dumps(body).encode("utf-8")


def plan_run(
    cases: Sequence[Case],
    arms: tuple[Arm, Arm],
    *,
    repetitions: int,
    model: str,
    temperature: str = "0",
) -> Plan:
    planned = [
        PlannedCase(
            case,
            {arm.name: arm.prepare(request_body(case, model, temperature)) for arm in arms},
        )
        for case in cases
    ]
    exercised = [p for p in planned if not p.not_exercised]
    return Plan(
        cases=planned,
        repetitions=repetitions,
        model=model,
        calls=len(exercised) * repetitions * len(arms),
        est_input_tokens=sum(
            p.prepared[arm.name].est_tokens * repetitions for p in exercised for arm in arms
        ),
    )


def _answer(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return ""
    return "\n".join(
        b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str)
    )


def _tool_calls(payload: Any) -> list[ToolCall]:
    blocks = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(blocks, list):
        return []
    return [
        (str(b.get("name")), b.get("input"))
        for b in blocks
        if isinstance(b, dict) and b.get("type") == "tool_use"
    ]


async def run_smoke(
    plan: Plan,
    arms: tuple[Arm, Arm],
    *,
    api_key: str,
    max_calls: int,
    progress: Callable[[int, int], None] | None = None,
) -> RunResult:
    """Runs every exercised case in both arms, repetition by repetition, and stops before the
    call that would exceed ``max_calls`` (QE-010, QE-018)."""
    upstream = arms[0].services.upstream
    headers = [
        ("x-api-key", api_key),
        ("anthropic-version", ANTHROPIC_VERSION),
        ("content-type", "application/json"),
        ("accept-encoding", "identity"),
    ]
    outcomes: dict[str, dict[str, list[str]]] = {
        p.case.case_id: {arm.name: [] for arm in arms} for p in plan.cases
    }
    result = RunResult()
    exact = {arm.name: 0 for arm in arms}
    estimate = {arm.name: 0 for arm in arms}
    consecutive_errors = 0
    await upstream.start()
    try:
        for repetition in range(plan.repetitions):
            for planned in plan.cases:
                if planned.not_exercised:
                    continue
                for arm in arms:
                    if result.calls >= max_calls:
                        result.stopped_by_cap = True
                        break
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        result.stopped_by_errors = True
                        break
                    prepared = planned.prepared[arm.name]
                    result.calls += 1
                    outcome, tokens, answer, status, error, stop = await _call(
                        upstream, headers, prepared.body, planned.case
                    )
                    if error is not None:
                        key = (error["type"], error["message"])
                        result.errors[key] = result.errors.get(key, 0) + 1
                    consecutive_errors = consecutive_errors + 1 if outcome == "error" else 0
                    outcomes[planned.case.case_id][arm.name].append(outcome)
                    if progress is not None:
                        progress(result.calls, min(plan.calls, max_calls))
                    estimate[arm.name] += prepared.est_tokens
                    exact[arm.name] += tokens or 0
                    result.rows.append(
                        {
                            "case_id": planned.case.case_id,
                            "arm": arm.name,
                            "repetition": repetition + 1,
                            "outcome": outcome,
                            "status": status,
                            "input_tokens": (
                                {"value": tokens, "method": "exact"}
                                if tokens is not None
                                else {"value": prepared.est_tokens, "method": "estimate"}
                            ),
                            "answer": answer[:_ANSWER_LIMIT],
                            "stop_reason": stop,  # S8c: diagnoses refusals and truncation
                            **({"error": error} if error is not None else {}),
                        }
                    )
                if result.stopped_by_cap or result.stopped_by_errors:
                    break
            if result.stopped_by_cap or result.stopped_by_errors:
                break
    finally:
        await upstream.aclose()
    for planned in plan.cases:
        seen = outcomes[planned.case.case_id]
        result.cases.append(
            CaseResult(
                case_id=planned.case.case_id,
                family=planned.case.family,
                assumption=planned.case.assumption,
                baseline=tuple(seen[arms[0].name]),
                candidate=tuple(seen[arms[1].name]),
                not_exercised=planned.not_exercised,
                repetitions=plan.repetitions,
            )
        )
    for arm in arms:
        result.totals[arm.name] = ArmTotals(
            exact=exact[arm.name],
            estimate=estimate[arm.name],
            ms_compressor=round(sum(p.prepared[arm.name].ms_compressor for p in plan.cases), 3),
        )
    return result


def _error(kind: str, message: str = "") -> dict[str, str]:
    return {"type": kind[:100], "message": message[:_MESSAGE_LIMIT]}


def _provider_error(payload: Any, status: int) -> dict[str, str]:
    """The provider's error type and message only (as OB-006 for the proxy); never the body."""
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return _error(str(error.get("type", f"http_{status}")), str(error.get("message", "")))
    return _error(f"http_{status}")


async def _call(
    upstream: Any, headers: list[tuple[str, str]], body: bytes, case: Case
) -> tuple[str, int | None, str, int | None, dict[str, str] | None, str | None]:
    """One provider call: (outcome, exact input tokens, answer text, status, error, stop reason)."""
    try:
        response = await upstream.open("POST", "/v1/messages", "", headers, body)
        try:
            data = await response.aread()
        finally:
            await response.aclose()
    except UpstreamError as exc:
        return "error", None, "", None, _error(exc.kind), None
    except OSError as exc:
        return "error", None, "", None, _error("connection_error", type(exc).__name__), None
    usage = BodyUsageParser(_RESPONSE_LIMIT)
    usage.feed(data)
    tokens = usage.result().input_total
    status = response.status_code
    try:
        payload = json.loads(data)
    except ValueError:
        return "error", tokens, "", status, _error(f"http_{status}", "response is not JSON"), None
    stop = payload.get("stop_reason") if isinstance(payload, dict) else None
    if status >= 400:
        return "error", tokens, "", status, _provider_error(payload, status), stop
    answer = _answer(payload)
    if payload.get("stop_reason") == "refusal":
        return "error", tokens, answer, status, _error("refusal"), stop
    if case.checker in TOOL_CHECKERS:  # S8c/S8e: a tool call can be the answer
        calls = _tool_calls(payload)
        if not answer and not calls:
            return "error", tokens, answer, status, _error("empty_answer"), stop
        seen = answer + "".join(f"\n[tool_use {name} {json.dumps(args)}]" for name, args in calls)
        passed = TOOL_CHECKERS[case.checker](answer, calls, case)
        return ("pass" if passed else "fail"), tokens, seen, status, None, stop
    if not answer:
        return "error", tokens, answer, status, _error("empty_answer"), stop
    passed = CHECKERS[case.checker](answer, case.expected)
    return ("pass" if passed else "fail"), tokens, answer, status, None, stop
