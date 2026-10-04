# S8a SCR-002 — Families that a compressor never exercises do not enter its verdict

Status: **approved 2026-10-04** ("approvo SCR-002"). Applied to SPEC 012 QE-015.

## 1. Affected requirements

- **SPEC 012 QE-015** (approved S2.5): the smoke verdict per family, and the overall verdict
  (`insufficient_data` when any family has fewer than `smoke_min_cases` completed cases).
- **SPEC 012 QE-012** (approved S2.5, S4): a smoke run loads every family whose assumption the
  compressor declares; unchanged cases are `not_exercised` and do not count towards n.
- The S8a-1 families approved at Gate 1. `grep_verbatim_quote` and `log_verbatim_quote` test
  `not_quoted_verbatim`, the assumption that every text-changing compressor declares.

## 2. Evidence

`tests/integration/test_eval.py` fails after the S8a-1 cases were added:

| Test | Failure |
|---|---|
| `test_smoke_harness_self_test` | family verdicts `{'insufficient_data', 'no_measurable_damage'}`, expected `{'no_measurable_damage'}` |
| `test_harness_uses_real_pipeline` | `88 == 2 * 88`: half the loaded cases are now unexercised |
| `test_smoke_arms_differ_only_in_candidate`, `test_harness_report_provenance` | the same cause |

The cause:
- the identity and `json_minify` self-tests now load `grep_verbatim_quote` and `log_verbatim_quote`;
- `json_minify` leaves all 44 of their cases unchanged, so they are `not_exercised`;
- each of those families has 0 completed cases, which gives `insufficient_data`;
- `overall_verdict` then returns `insufficient_data`.

The same happens to `search_group` with the log families and to `log_filter` with the grep
families. Under the approved texts, **no compressor that declares `not_quoted_verbatim` can reach
`no_measurable_damage` any more.**

## 3. Why the current requirement should change

A family in which the candidate changes no case says nothing about that compressor: neither
damage nor its absence. Treating it as "insufficient data" makes evidence for the compressor
impossible, even when the families it does exercise are complete.

## 4. Proposed change

Add to **QE-015**:

> A family in which no case is exercised SHALL be reported as `not_exercised` and SHALL NOT
> enter the overall verdict. THE overall verdict SHALL be `insufficient_data` when a declared
> assumption of the compressor has no family with at least one exercised case. (S8a SCR-002.)

Everything else in QE-015 is unchanged. A family with *some* exercised cases still needs
`smoke_min_cases` completed cases.

## 5. Impact on tests

New:
- `test_unexercised_family_does_not_enter_verdict`;
- `test_assumption_without_exercised_family_is_insufficient`.

The first version of this section said the four `test_eval.py` tests would pass again
unchanged. That was wrong: their helper assumed every loaded family is exercised, and they
counted calls as `2 × all cases`. They now:
- separate the exercised families and assert that the unexercised ones are exactly
  `grep_verbatim_quote` and `log_verbatim_quote`;
- count calls on exercised cases only, with `not_exercised == 44` asserted;
- check the overall verdict with the declared assumptions.

These assertions are stricter than before.

The run record lists in `assumptions_covered` only the assumptions of families with an exercised
case. The provenance lists every case set loaded.

## 6. Impact on architecture

`tokli.eval.verdict` (`family_verdict` gains the `not_exercised` value, and `overall_verdict`
receives the declared assumptions). The report lists unexercised families separately.

## 7. Compatibility and migration

- The existing records (`json_minify`, `duplicate_tool_results`) remain valid, because they were
  computed before these families existed. A new run of `json_minify` loads 44 more cases, which
  make no provider calls (QE-012).
- No persisted schema, config key or fingerprint change.
