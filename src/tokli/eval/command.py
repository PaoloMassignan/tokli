"""`tokli eval smoke` (QE-009…QE-012, QE-018, QE-019). Manual only: nothing else starts it."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tokli.app.bootstrap import Services, StartupError
from tokli.compression.registry import REGISTRY
from tokli.config import EffectiveConfig
from tokli.eval.cases import load_cases
from tokli.eval.record import Provenance, write_results
from tokli.eval.runner import Arm, call_ceiling, plan_run, run_smoke
from tokli.eval.verdict import FamilyVerdict, family_verdict, overall_verdict


@dataclass(frozen=True)
class SmokeOptions:
    compressor: str
    model: str
    api_key_env: str
    max_calls: int | None
    repetitions: int
    yes: bool
    temperature: str
    evals_dir: Path
    tokli_version: str
    max_cost: Decimal | None = None  # USD (QE-009, S6)


def arm_sets(compressor: str, candidate: bool) -> tuple[str, ...]:
    """Config overrides for an arm: every compressor off, plus ``compressor`` on in the
    candidate (QE-012)."""
    values = {
        c.spec.id: "true" if candidate and c.spec.id == compressor else "false" for c in REGISTRY
    }
    return tuple(f"compressors.{cid}.enabled={value}" for cid, value in values.items())


def smoke(
    options: SmokeOptions,
    baseline_config: EffectiveConfig,
    candidate_config: EffectiveConfig,
    build: Callable[..., Services],
    out: Callable[[str], None],
    ask: Callable[[str], str],
) -> int:
    spec = next((c.spec for c in REGISTRY if c.spec.id == options.compressor), None)
    if spec is None:
        known = ", ".join(c.spec.id for c in REGISTRY)
        raise StartupError(f"unknown compressor '{options.compressor}'", f"use one of: {known}")
    key = os.environ.get(options.api_key_env, "")
    if not key:
        raise StartupError(
            f"the environment variable {options.api_key_env} is not set or empty",
            f"set {options.api_key_env} to an Anthropic API key in this terminal",
        )
    cases = load_cases(options.evals_dir / "cases", spec.assumptions)
    if not cases:
        raise StartupError(
            f"no cases for the assumptions of '{spec.id}' in {options.evals_dir / 'cases'}",
            "check --evals-dir",
        )
    arms = (
        Arm("baseline", build(baseline_config, telemetry=False)),
        Arm("candidate", build(candidate_config, telemetry=False)),
    )
    match = arms[0].services.prices.lookup(options.model, datetime.now(UTC))
    if match is None and options.max_calls is None:
        raise StartupError(
            f"no price for '{options.model}' in the price book, so a cost cap in money is not "
            "possible (QE-011)",
            "add --max-calls N; the plan printed by this command shows how many calls a run needs",
        )
    if match is not None and options.yes and options.max_cost is None and options.max_calls is None:
        raise StartupError(
            "--yes needs a cap: --max-cost <USD> or --max-calls N (QE-009)",
            "run without --yes to see the estimated cost, or add --max-cost",
        )
    plan = plan_run(
        cases,
        arms,
        repetitions=options.repetitions,
        model=options.model,
        temperature=options.temperature,
    )
    exercised = len(plan.cases) - plan.not_exercised
    out(f"Smoke evaluation of {spec.id} v{spec.version} on {options.model}")
    out(
        f"Plan: {exercised} cases ({plan.not_exercised} not exercised) x {options.repetitions} "
        f"repetitions x 2 arms = {plan.calls} calls; call cap {options.max_calls}"
    )
    out(f"estimated input tokens: {plan.est_input_tokens:,} (local estimate)")
    cost_cap: Decimal | None = None
    if match is not None:
        ceiling = sum(
            (
                call_ceiling(match.prices, planned.prepared[arm.name]) * options.repetitions
                for planned in plan.cases
                if not planned.not_exercised
                for arm in arms
            ),
            Decimal(0),
        )
        cost_cap = options.max_cost if options.max_cost is not None else ceiling * Decimal("1.2")
        out(
            f"estimated cost: at most ${ceiling:.4f} (an upper bound: input at the uncached price "
            f"plus max_tokens of output per call; price book {match.version}); "
            f"cost cap ${cost_cap:.4f}"
        )
    if not options.yes:
        try:
            answer = ask("Proceed? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            raise StartupError("cancelled: no provider call was made", "run again and answer y")

    def progress(done: int, total: int) -> None:
        if done % 10 == 0 or done == total:
            out(f"progress: {done}/{total} calls")

    result = asyncio.run(
        run_smoke(
            plan,
            arms,
            api_key=key,
            max_calls=options.max_calls if options.max_calls is not None else plan.calls,
            progress=progress,
            prices=match.prices if match is not None else None,
            cost_cap=cost_cap,
        )
    )
    families = _families(result.cases)
    verdict = overall_verdict(families, spec.assumptions)
    provenance = Provenance(
        tokli_version=options.tokli_version,
        compressor=spec.id,
        compressor_version=spec.version,
        model=options.model,
        date=datetime.now(UTC).date().isoformat(),
        case_set=", ".join(sorted({case.case_set for case in cases})),
        repetitions=options.repetitions,
        temperature=options.temperature,
        config_hash_baseline=baseline_config.config_hash,
        config_hash_candidate=candidate_config.config_hash,
    )
    record, report = write_results(
        options.evals_dir,
        provenance,
        families,
        verdict,
        result.rows,
        result.totals,
        calls=result.calls,
        stopped_by_cap=result.stopped_by_cap,
        stopped_by_errors=result.stopped_by_errors,
        errors=result.errors,
    )
    if result.stopped_by_errors:
        out("stopped after 10 consecutive errors: the run cannot judge the compressor")
    if result.stopped_by_cost:
        out(f"stopped by the cost cap: ${result.spent:.4f} spent, from provider usage")
    for (kind, message), count in sorted(result.errors.items(), key=lambda item: -item[1]):
        out(f"  errors: {count} x {kind}" + (f": {message}" if message else ""))
    for family in families:
        out(
            f"  {family.family}: n={family.n} b={family.b} c={family.c} "
            f"not_exercised={family.not_exercised} -> {family.verdict}"
        )
    out(
        f"Verdict: {verdict} ({result.calls} calls"
        + (", stopped by the cap)" if result.stopped_by_cap else ")")
    )
    out(f"record: {record}")
    out(f"report: {report}")
    return 0


def _families(results: list[Any]) -> list[FamilyVerdict]:
    grouped: dict[str, list[Any]] = {}
    for item in results:
        grouped.setdefault(item.family, []).append(item)
    return [family_verdict(items) for items in grouped.values()]
