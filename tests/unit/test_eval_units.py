"""SPEC 012 smoke tier, pure parts: checkers (QE-020), case lint (QE-013), verdict (QE-015),
records (QE-016)."""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from tokli.compression.registry import REGISTRY
from tokli.eval.cases import lint_case, lint_tree, load_cases
from tokli.eval.checkers import CHECKERS, exact_value, json_structural
from tokli.eval.record import record_problems
from tokli.eval.verdict import CaseResult, family_verdict, overall_verdict

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evals" / "cases"
P, F, E = "pass", "fail", "error"


# -- checkers (QE-020) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer, ok",
    [
        ("SKU-48213", True),
        ("  SKU-48213  \n", True),
        ("`SKU-48213`", True),
        ('"SKU-48213"', True),
        ("The SKU is:\n\nSKU-48213", True),  # the last non-empty line counts
        ("SKU-48213.", False),
        ("SKU-4821", False),
        ("**SKU-48213**", False),
        ("", False),
    ],
)
def test_checker_exact_value(answer: str, ok: bool) -> None:
    assert exact_value(answer, "SKU-48213") is ok


EXPECTED_JSON = '{"id": 7, "tags": ["a", "b"], "loc": {"aisle": 3, "shelf": "B"}}'


@pytest.mark.parametrize(
    "answer, ok",
    [
        ('{"loc":{"shelf":"B","aisle":3},"id":7,"tags":["a","b"]}', True),  # key order, spaces
        (
            'Here it is:\n```json\n{\n  "id": 7,\n  "tags": ["a", "b"],\n'
            '  "loc": {"aisle": 3, "shelf": "B"}\n}\n```',
            True,
        ),
        ('{"id": 7, "tags": ["b", "a"], "loc": {"aisle": 3, "shelf": "B"}}', False),  # list order
        ('{"id": "7", "tags": ["a", "b"], "loc": {"aisle": 3, "shelf": "B"}}', False),  # type
        ('{"id": 7, "tags": ["a", "b"]}', False),
        ("no json here", False),
        ('{"id": 7, "tags": ["a", "b"], "loc": {"aisle": 3, "shelf": "B"}', False),  # truncated
    ],
)
def test_checker_json_structural(answer: str, ok: bool) -> None:
    assert json_structural(answer, EXPECTED_JSON) is ok


def test_checker_registry_is_closed() -> None:
    assert set(CHECKERS) == {"exact_value", "json_structural", "verbatim_line"}


# -- cases (QE-013, AC-QE-6) -------------------------------------------------------------------


def a_case() -> dict[str, Any]:
    return yaml.safe_load((CASES / "json_fact_lookup" / "01.yaml").read_text(encoding="utf-8"))


def test_eval_cases_lint() -> None:
    assert lint_tree(CASES) == []  # the committed cases are clean
    good = a_case()
    assert lint_case(good, "x") == []
    for field in ("assumption", "checker", "expected", "request", "family", "case_set"):
        broken = copy.deepcopy(good)
        del broken[field]
        assert any(field in e for e in lint_case(broken, "x")), field
    unknown = copy.deepcopy(good)
    unknown["checker"] = "fuzzy_match"
    assert lint_case(unknown, "x")
    with_model = copy.deepcopy(good)
    with_model["request"]["model"] = "claude-x"
    assert any("model" in e for e in lint_case(with_model, "x"))
    users = "Us" + "ers"  # built at run time: this file itself must contain no such path (MD-27)
    for canary in (
        f"C:\\{users}\\someone\\repo",
        "/ho" + "me/someone/repo",
        f"/{users}/someone/x",
        "sk-ant-api03-abc",
    ):
        leaky = copy.deepcopy(good)
        leaky["request"]["messages"][0]["content"] = f"look at {canary}"
        assert any("forbidden" in e for e in lint_case(leaky, "x")), canary


def test_cases_load_by_assumption() -> None:
    spec = next(c.spec for c in REGISTRY if c.spec.id == "json_minify")
    cases = load_cases(CASES, spec.assumptions)
    families = {c.family for c in cases}
    assert families == {"json_fact_lookup", "json_verbatim_quote"}
    assert sum(1 for c in cases if c.family == "json_fact_lookup") >= 20
    assert load_cases(CASES, ("an_assumption_without_cases",)) == []
    assert all(c.case_id.startswith(f"{c.family}/") for c in cases)


# -- verdict (QE-015, AC-QE-5) -----------------------------------------------------------------


def results(n: int, *, b: int = 0, c: int = 0, **extra: Any) -> list[CaseResult]:
    """n completed cases: b pass→fail, c fail→pass, the rest pass in both arms."""
    out = []
    for i in range(n):
        base, cand = (P, P, P), (P, P, P)
        if i < b:
            cand = (F, F, P)  # majority fail
        elif i < b + c:
            base = (F, P, F)
        out.append(CaseResult(f"fam/{i:02d}", "fam", "assume", base, cand, **extra))
    return out


def test_smoke_verdict_rule() -> None:
    assert family_verdict(results(20, b=2)).verdict == "damage_detected"
    one = family_verdict(results(20, b=1))
    assert one.verdict == "no_measurable_damage" and (one.n, one.b, one.c) == (20, 1, 0)
    assert family_verdict(results(20, b=3, c=2)).verdict == "no_measurable_damage"  # b - c = 1
    errors = results(20)
    for i in range(2):
        errors[i] = dataclasses.replace(errors[i], candidate=(E, E, P))
    assert family_verdict(errors).verdict == "damage_detected"  # 2 more candidate errors
    errors[1] = dataclasses.replace(errors[1], candidate=(P, P, P))
    assert family_verdict(errors).verdict == "no_measurable_damage"  # 1 more is tolerated


def test_smoke_insufficient_data() -> None:
    assert family_verdict(results(19)).verdict == "insufficient_data"
    incomplete = results(20)
    incomplete[0] = dataclasses.replace(incomplete[0], candidate=(P, P))  # stopped by the cap
    verdict = family_verdict(incomplete)
    assert verdict.verdict == "insufficient_data" and verdict.incomplete == 1


def test_case_not_exercised_is_excluded() -> None:
    cases = [
        *results(20),
        CaseResult("fam/99", "fam", "assume", (P, P, P), (P, P, P), not_exercised=True),
    ]
    verdict = family_verdict(cases)
    assert verdict.n == 20 and verdict.not_exercised == 1
    assert family_verdict(results(19) + cases[-1:]).verdict == "insufficient_data"


def test_overall_verdict() -> None:
    ok = family_verdict(results(20))
    bad = family_verdict(results(20, b=2))
    few = family_verdict(results(5))
    assert overall_verdict([ok, ok]) == "no_measurable_damage"
    assert overall_verdict([ok, few]) == "insufficient_data"
    assert overall_verdict([few, bad]) == "damage_detected"


# -- records (QE-016, AC-QE-7) -----------------------------------------------------------------


def record(**values: Any) -> dict[str, Any]:
    base = {
        "compressor": "json_minify",
        "version": "1",
        "tier": "smoke",
        "assumptions_covered": ["reads_minified_json", "not_quoted_verbatim"],
        "verdict": "no_measurable_damage",
        "model": "claude-x",
        "date": "2026-10-03",
        "report": "results/2026-10-03-json_minify-claude-x/report.md",
    }
    base.update(values)
    return base


def test_eval_record_schema_and_provisional_rule() -> None:
    spec = next(c.spec for c in REGISTRY if c.spec.id == "json_minify")
    assert record_problems(record(), spec) == []
    other = dataclasses.replace(spec, id="other_compressor")
    assert record_problems(record(compressor="other_compressor", tier="provisional"), other)
    assert (
        record_problems(record(tier="provisional", verdict=None), spec, allow_provisional=True)
        == []
    )
    assert record_problems(record(tier="provisional", verdict=None), spec)  # after S2.5 exit
    assert record_problems(record(verdict="damage_detected"), spec)
    assert record_problems(record(tier="weekly"), spec)
    missing = record()
    del missing["model"]
    assert record_problems(missing, spec)


def test_eval_record_invalidated_by_version_bump() -> None:
    spec = next(c.spec for c in REGISTRY if c.spec.id == "json_minify")
    bumped = dataclasses.replace(spec, version="2")
    assert record_problems(record(), bumped)


def test_all_errors_is_insufficient_data_not_a_pass() -> None:
    """Regression (found in the first real smoke run, 2026-10-03): every call answered 400, yet
    the verdict was `no_measurable_damage`. Root cause: errored cases counted as completed, and
    equal error counts in both arms satisfied the error rule. QE-007: no quality figure without
    enough cases that succeeded, so cases whose baseline errors do not count towards n."""
    errored = [CaseResult(f"fam/{i:02d}", "fam", "assume", (E, E, E), (E, E, E)) for i in range(22)]
    verdict = family_verdict(errored)
    assert verdict.verdict == "insufficient_data"
    assert verdict.n == 0 and verdict.errors_baseline == 22
    mostly = results(20) + errored[:5]
    assert family_verdict(mostly).verdict == "no_measurable_damage"  # 20 good cases suffice


# -- S4: verbatim_line (QE-020) and the reference families --------------------------------------


@pytest.mark.parametrize(
    "answer, ok",
    [
        ("    timeout = 30", True),
        ("Here is the line:\n\n    timeout = 30", True),
        ("```\n    timeout = 30\n```", True),  # fences are not lines
        ("```toml\n    timeout = 30\n```", True),
        ("`    timeout = 30`", True),
        ("    timeout = 30\r", True),  # a CR line ending is not content
        ("timeout = 30", False),  # leading whitespace lost: not an edit anchor
        ("     timeout = 30", False),
        ("    timeout = 30 ", False),
        ("    12\t    timeout = 30", False),  # the line-number prefix is not part of the file
        ("", False),
    ],
)
def test_checker_verbatim_line(answer: str, ok: bool) -> None:
    assert CHECKERS["verbatim_line"](answer, "    timeout = 30") is ok


def test_reference_families_exist_for_the_pruner() -> None:
    spec = next(c.spec for c in REGISTRY if c.spec.id == "duplicate_tool_results")
    cases = load_cases(CASES, spec.assumptions)
    counts = {f: sum(1 for c in cases if c.family == f) for f in {c.family for c in cases}}
    assert counts == {"reference_fact_lookup": 22, "reference_verbatim_quote": 22}
    assert {c.checker for c in cases} == {"exact_value", "verbatim_line"}
