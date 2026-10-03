"""Evaluation records and reports (QE-005, QE-014, QE-016).

The record (``records/<compressor>.yaml``) is what CC-020 checks. The report (``results/<run>/
report.md``) is the human-readable summary with provenance; ``cases.jsonl`` holds the per-case
outcomes and raw answers and is not committed (ADR 0008).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tokli.compression.contract import CompressorSpec
from tokli.eval.verdict import FamilyVerdict

FIELDS = (
    "compressor",
    "version",
    "tier",
    "assumptions_covered",
    "verdict",
    "model",
    "date",
    "report",
)
TIERS = ("smoke", "full", "provisional")


def record_problems(
    record: Mapping[str, Any], spec: CompressorSpec, *, allow_provisional: bool = False
) -> list[str]:
    """Why ``record`` cannot justify enabling ``spec`` by default (CC-020, QE-016)."""
    problems = [f"missing field '{name}'" for name in FIELDS if name not in record]
    if problems:
        return problems
    if record["compressor"] != spec.id:
        problems.append(f"record is for '{record['compressor']}', not '{spec.id}'")
    if str(record["version"]) != spec.version:
        problems.append(
            f"record is for version {record['version']}, the compressor is {spec.version}"
        )
    tier = record["tier"]
    if tier not in TIERS:
        problems.append(f"unknown tier '{tier}'")
    elif tier == "provisional":
        if not (allow_provisional and spec.id == "json_minify"):
            problems.append("a provisional record is not allowed (QE-016)")
    elif record["verdict"] != "no_measurable_damage":
        problems.append(f"verdict is '{record['verdict']}'")
    missing = set(spec.assumptions) - set(record["assumptions_covered"] or ())
    if tier != "provisional" and missing:
        problems.append("assumptions not covered: " + ", ".join(sorted(missing)))
    return problems


@dataclass(frozen=True)
class Provenance:
    tokli_version: str
    compressor: str
    compressor_version: str
    model: str
    date: str
    case_set: str
    repetitions: int
    temperature: str
    config_hash_baseline: str
    config_hash_candidate: str


@dataclass(frozen=True)
class ArmTotals:
    exact: int
    estimate: int
    ms_compressor: float


def run_folder(evals_dir: Path, provenance: Provenance) -> Path:
    safe_model = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in provenance.model)
    return evals_dir / "results" / f"{provenance.date}-{provenance.compressor}-{safe_model}"


def write_results(
    evals_dir: Path,
    provenance: Provenance,
    families: Sequence[FamilyVerdict],
    verdict: str,
    rows: Sequence[Mapping[str, Any]],
    totals: Mapping[str, ArmTotals],
    *,
    calls: int,
    stopped_by_cap: bool,
    stopped_by_errors: bool = False,
    errors: Mapping[tuple[str, str], int] | None = None,
) -> tuple[Path, Path]:
    """Writes the report, the per-case rows and the record. Returns (record, report)."""
    folder = run_folder(evals_dir, provenance)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "cases.jsonl").open("w", encoding="utf-8", newline="\n") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    report = folder / "report.md"
    report.write_text(
        _report(
            provenance,
            families,
            verdict,
            totals,
            calls,
            stopped_by_cap,
            stopped_by_errors,
            errors or {},
        ),
        encoding="utf-8",
        newline="\n",
    )
    record = {
        "compressor": provenance.compressor,
        "version": provenance.compressor_version,
        "tier": "smoke",
        "assumptions_covered": [f.assumption for f in families],
        "verdict": verdict,
        "model": provenance.model,
        "date": provenance.date,
        "report": report.relative_to(evals_dir).as_posix(),
    }
    target = evals_dir / "records" / f"{provenance.compressor}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    header = "# Evaluation record (SPEC 012, QE-016), written by `tokli eval smoke`.\n"
    target.write_text(
        header + yaml.safe_dump(record, sort_keys=False), encoding="utf-8", newline="\n"
    )
    return target, report


def _report(
    p: Provenance,
    families: Sequence[FamilyVerdict],
    verdict: str,
    totals: Mapping[str, ArmTotals],
    calls: int,
    stopped_by_cap: bool,
    stopped_by_errors: bool,
    errors: Mapping[tuple[str, str], int],
) -> str:
    lines = [
        f"# Smoke evaluation: {p.compressor} on {p.model}",
        "",
        f"**Verdict: {verdict}.** The smoke tier detects only gross damage (SPEC 012, QE-015).",
        "",
        "## Provenance",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Tokli version | {p.tokli_version} |",
        f"| Compressor | {p.compressor} v{p.compressor_version} |",
        f"| Model | {p.model} |",
        f"| Date | {p.date} |",
        f"| Version of the case set | {p.case_set} |",
        f"| Repetitions | {p.repetitions} |",
        f"| Temperature | {'model default' if p.temperature == 'default' else p.temperature} |",
        f"| config_hash baseline | {p.config_hash_baseline} |",
        f"| config_hash candidate | {p.config_hash_candidate} |",
        f"| Provider calls | {calls}"
        + (" (stopped by the call cap)" if stopped_by_cap else "")
        + (" (stopped after 10 consecutive errors)" if stopped_by_errors else "")
        + " |",
        "",
        "## Results per assumption",
        "",
        "| Family | Assumption | n | b (pass → fail) | c (fail → pass) | errors baseline | "
        "errors candidate | not exercised | incomplete | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for f in families:
        lines.append(
            f"| {f.family} | {f.assumption} | {f.n} | {f.b} | {f.c} | {f.errors_baseline} | "
            f"{f.errors_candidate} | {f.not_exercised} | {f.incomplete} | {f.verdict} |"
        )
    if errors:
        lines += ["", "## Errors", "", "| Count | Type | Provider message |", "|---|---|---|"]
        for (kind, message), count in sorted(errors.items(), key=lambda item: -item[1]):
            lines.append(f"| {count} | {kind} | {message.replace('|', '/')} |")
    base, cand = totals.get("baseline"), totals.get("candidate")
    lines += ["", "## Tokens and time", ""]
    if base and cand:
        lines += [
            "| | baseline | candidate |",
            "|---|---|---|",
            f"| forwarded input tokens, exact (provider usage) | {base.exact:,} | {cand.exact:,} |",
            f"| forwarded input tokens, estimate (local) | {base.estimate:,} | {cand.estimate:,} |",
            f"| compressor time (ms, total) | {base.ms_compressor:.1f} | "
            f"{cand.ms_compressor:.1f} |",
            "",
            f"Estimated saving: {base.estimate - cand.estimate:,} tokens "
            f"({_pct(base.estimate - cand.estimate, base.estimate)} of the baseline estimate); "
            f"exact difference from provider usage: {base.exact - cand.exact:,} tokens.",
        ]
    lines += [
        "",
        "A case passes in an arm when most of its repetitions pass. The verdict is "
        "`no_measurable_damage` when b - c <= 1 and the candidate has at most one more errored "
        "case than the baseline, over at least 20 completed cases.",
        "",
    ]
    return "\n".join(lines)


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "n/a"
