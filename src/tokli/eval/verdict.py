"""Smoke verdict (QE-015). It detects gross damage only."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

SMOKE_MIN_CASES = 20


@dataclass(frozen=True)
class CaseResult:
    """Outcomes per repetition in each arm (``pass``/``fail``/``error``). An arm with fewer
    outcomes than repetitions was stopped by the call cap."""

    case_id: str
    family: str
    assumption: str
    baseline: tuple[str, ...]
    candidate: tuple[str, ...]
    not_exercised: bool = False
    repetitions: int = 3


@dataclass(frozen=True)
class FamilyVerdict:
    family: str
    assumption: str
    n: int
    b: int
    c: int
    errors_baseline: int
    errors_candidate: int
    not_exercised: int
    incomplete: int
    verdict: str


def _majority(outcomes: Sequence[str], value: str) -> bool:
    return sum(1 for o in outcomes if o == value) * 2 > len(outcomes)


def _complete(result: CaseResult) -> bool:
    expected = max(result.repetitions, len(result.baseline), len(result.candidate))
    return len(result.baseline) == len(result.candidate) == expected


def family_verdict(
    results: Sequence[CaseResult], min_cases: int = SMOKE_MIN_CASES
) -> FamilyVerdict:
    """A case passes in an arm when most repetitions pass; b = pass in the baseline and not in
    the candidate, c = the reverse. With n >= ``min_cases`` completed cases: no damage iff
    b - c <= 1 and the candidate has at most one more errored case than the baseline."""
    exercised = [r for r in results if not r.not_exercised]
    complete = [r for r in exercised if _complete(r)]
    # QE-007: a case whose baseline errored says nothing about the compressor; it is reported
    # in the error counts but never counted as a completed case.
    judged = [r for r in complete if not _majority(r.baseline, "error")]
    b = sum(
        1 for r in judged if _majority(r.baseline, "pass") and not _majority(r.candidate, "pass")
    )
    c = sum(
        1 for r in judged if not _majority(r.baseline, "pass") and _majority(r.candidate, "pass")
    )
    errors_baseline = sum(1 for r in complete if _majority(r.baseline, "error"))
    errors_candidate = sum(1 for r in complete if _majority(r.candidate, "error"))
    if results and not exercised:
        verdict = "not_exercised"  # S8a SCR-002: says nothing about this compressor
    elif len(judged) < min_cases:
        verdict = "insufficient_data"
    elif b - c <= 1 and errors_candidate - errors_baseline <= 1:
        verdict = "no_measurable_damage"
    else:
        verdict = "damage_detected"
    first = results[0] if results else None
    return FamilyVerdict(
        family=first.family if first else "",
        assumption=first.assumption if first else "",
        n=len(judged),
        b=b,
        c=c,
        errors_baseline=errors_baseline,
        errors_candidate=errors_candidate,
        not_exercised=len(results) - len(exercised),
        incomplete=len(exercised) - len(complete),
        verdict=verdict,
    )


def overall_verdict(
    families: Sequence[FamilyVerdict], assumptions: Sequence[str] | None = None
) -> str:
    """Damage in any family wins; then missing data; otherwise no measurable damage. Families
    with no exercised case stay out, but every declared assumption needs at least one family
    with an exercised case (QE-015 after S8a SCR-002)."""
    judged = [f for f in families if f.verdict != "not_exercised"]
    verdicts = {f.verdict for f in judged}
    if "damage_detected" in verdicts:
        return "damage_detected"
    if not judged or "insufficient_data" in verdicts:
        return "insufficient_data"
    covered = {f.assumption for f in judged}
    if assumptions is not None and not set(assumptions) <= covered:
        return "insufficient_data"
    return "no_measurable_damage"
