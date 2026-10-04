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
    # QE-012: every family whose assumption the compressor declares. S8a-1 added two more
    # families for `not_quoted_verbatim`; for json_minify they are not exercised (no JSON).
    assert families == {
        "json_fact_lookup",
        "json_verbatim_quote",
        "grep_verbatim_quote",
        "log_verbatim_quote",
    }
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


def unexercised(n: int, family: str = "other", assumption: str = "assume") -> list[CaseResult]:
    return [
        CaseResult(f"{family}/{i:02d}", family, assumption, (), (), not_exercised=True)
        for i in range(n)
    ]


def test_unexercised_family_does_not_enter_verdict() -> None:
    """QE-015 after S8a SCR-002: a family in which no case is exercised is `not_exercised`
    and stays out of the overall verdict; a family with some exercised cases still needs
    `smoke_min_cases` completed ones."""
    idle = family_verdict(unexercised(22))
    assert idle.verdict == "not_exercised" and idle.not_exercised == 22 and idle.n == 0
    ok = family_verdict(results(20))
    assert overall_verdict([ok, idle], assumptions=("assume",)) == "no_measurable_damage"
    partly = family_verdict(results(5) + unexercised(17, family="fam"))
    assert partly.verdict == "insufficient_data"


def test_assumption_without_exercised_family_is_insufficient() -> None:
    """QE-015 after S8a SCR-002: every declared assumption needs at least one family with an
    exercised case."""
    ok = family_verdict(results(20))
    idle = family_verdict(unexercised(22, assumption="other_assumption"))
    assert overall_verdict([ok, idle], assumptions=("assume", "other_assumption")) == (
        "insufficient_data"
    )
    bad = family_verdict(results(20, b=2))
    assert overall_verdict([bad, idle], assumptions=("assume", "other_assumption")) == (
        "damage_detected"
    )


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


# -- S8a-1: grep and log families (SPEC 012) -----------------------------------------------------


def _tool_results(case: Any) -> list[tuple[str, str]]:
    """(tool name, result text) for every tool result of a case's request."""
    names = {
        block["id"]: block["name"]
        for message in case.request["messages"]
        if message["role"] == "assistant" and isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_use"
    }
    return [
        (names[block["tool_use_id"]], block["content"])
        for message in case.request["messages"]
        if message["role"] == "user" and isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]


@pytest.mark.parametrize(
    "cid, own",
    [
        (
            "search_group",
            {"grep_fact_lookup": "exact_value", "grep_verbatim_quote": "verbatim_line"},
        ),
        ("log_filter", {"log_fact_lookup": "exact_value", "log_verbatim_quote": "verbatim_line"}),
    ],
)
def test_s8a1_families_exist(cid: str, own: dict[str, str]) -> None:
    """SPEC 012 S8a-1 families: 22 cases each (>= smoke_min_cases), with their checker."""
    spec = next(c.spec for c in REGISTRY if c.spec.id == cid)
    cases = load_cases(CASES, spec.assumptions)
    for family, checker in own.items():
        mine = [c for c in cases if c.family == family]
        assert len(mine) == 22, family
        assert {c.checker for c in mine} == {checker}


@pytest.mark.parametrize(
    "families, cid",
    [
        (("grep_fact_lookup", "grep_verbatim_quote"), "search_group"),
        (("log_fact_lookup", "log_verbatim_quote"), "log_filter"),
    ],
)
def test_s8a1_cases_exercise_their_compressor(families: tuple[str, ...], cid: str) -> None:
    """The cases put their content in a tool outside the default `verbatim_tools`, and the
    compressor applies to it, so the smoke candidate arm is exercised with default options."""
    from tests.helpers import FakeCounter
    from tokli.compression.contract import SegmentView
    from tokli.compression.engine import _features
    from tokli.config.schema import TokliSettings
    from tokli.domain.models import SegmentKind

    verbatim = set(TokliSettings().compression.verbatim_tools)
    compressor = next(c for c in REGISTRY if c.spec.id == cid)
    cases = [c for c in load_cases(CASES, compressor.spec.assumptions) if c.family in families]
    assert cases
    for case in cases:
        results = _tool_results(case)
        assert results, case.case_id
        exercised = False
        for name, text in results:
            assert name not in verbatim, case.case_id
            view = SegmentView(SegmentKind.TOOL_RESULT, "user", name, False, ())
            if compressor.applicable(text, view, _features(text, FakeCounter())).ok:
                exercised = True
        assert exercised, case.case_id


@pytest.mark.parametrize(
    "families, cid",
    [
        (("log_fact_lookup", "log_verbatim_quote"), "search_group"),
        (("grep_fact_lookup", "grep_verbatim_quote"), "log_filter"),
    ],
)
def test_s8a1_cases_do_not_exercise_the_other_compressor(
    families: tuple[str, ...], cid: str
) -> None:
    """S8a SCR-003: `search_group` leaves the log cases alone (timestamps are not grep lines),
    and `log_filter` leaves the grep cases alone, so a smoke run only spends calls on its own
    families."""
    from tests.helpers import FakeCounter
    from tokli.compression.contract import SegmentView
    from tokli.compression.engine import _features
    from tokli.domain.models import SegmentKind

    compressor = next(c for c in REGISTRY if c.spec.id == cid)
    cases = [
        c
        for c in load_cases(
            CASES, ("omitted_log_lines_not_needed", "reads_grouped_search", "not_quoted_verbatim")
        )
        if c.family in families
    ]
    assert cases
    for case in cases:
        for name, text in _tool_results(case):
            view = SegmentView(SegmentKind.TOOL_RESULT, "user", name, False, ())
            assert not compressor.applicable(text, view, _features(text, FakeCounter())).ok, (
                case.case_id
            )
