# S2.5 — Completion report

Slice: **S2.5 — Minimal evaluation skeleton (smoke tier)**. Branch `s2.5-smoke-eval`.
Gate 1: approved 2026-10-03 ("approvo s2.5"), see `SPEC_REVIEW.md`. Spec change: SCR-001
(temperature), approved 2026-10-03.

## Requirements implemented

- **SPEC 012:** QE-001, QE-004, QE-005, QE-007, QE-009…QE-011 (through QE-018 until a price book
  exists), QE-012…QE-020; case families `json_fact_lookup` and `json_verbatim_quote`.
- **SPEC 009:** CC-020 without the `provisional` exception (the S2.5 exit, QE-016).

**Deferred, as approved:**
- S8: QE-002, QE-003, QE-006, QE-008, generators and bootstrap CIs;
- S4: the `reference_*` families;
- S6: money caps (`--max-cost`).

## Exit criteria

1. **The harness self-test is green in CI (QE-017):** `test_smoke_harness_self_test` runs the real
   runner and the real case files against a fake model:
   - the content-identity compressor gives `no_measurable_damage`;
   - the digit-dropping compressor gives `damage_detected`.
2. **`json_minify` has a real smoke record replacing its provisional one:**
   `evals/records/json_minify.yaml` (tier `smoke`, verdict `no_measurable_damage`, model
   `claude-opus-5-5`, both assumptions covered). Report:
   `evals/results/2026-10-03-json_minify-claude-opus-5-5/report.md`. `json_minify` stays
   default-enabled.

## The real run, 2026-10-03

Run by the product owner (`tokli eval smoke --compressor json_minify --model claude-opus-5-5
--temperature default --max-calls 300`): 264 calls, all answered.

| Family | n | b | c | errors baseline | errors candidate | verdict |
|---|---|---|---|---|---|---|
| `json_fact_lookup` | 22 | 0 | 0 | 0 | 0 | `no_measurable_damage` |
| `json_verbatim_quote` | 22 | 0 | 0 | 0 | 0 | `no_measurable_damage` |

- **Outcomes:**
  - candidate: 132 of 132 pass;
  - baseline: 130 pass and 2 empty answers. These are `error` outcomes in two repetitions; no
    case has a majority error.
- **Tokens:**

  | | baseline | candidate |
  |---|---|---|
  | Forwarded input, exact (provider usage) | 297,561 | 217,437 |
  | Forwarded input, estimate (local) | 205,533 | 127,686 |

  The exact saving is **80,124 tokens (26.9 %)** on these JSON-heavy cases. The compressor's
  total time was 10 ms.
- **Scope of the conclusion:** these cases are deliberately JSON-heavy. The smoke tier detects
  only gross damage, and the saving here says nothing about savings on real Claude Code traffic,
  which the dogfood measures.

## Findings during the real run (fixed before the valid run)

1. **All 264 calls rejected, yet a verdict was given.** The first attempt was rejected with 400
   on every call, and the harness still reported `no_measurable_damage`. Root cause: errored
   cases counted as completed, and equal error counts satisfied the error rule. Fix (commit
   c685bea, regression tests `test_all_errors_is_insufficient_data_not_a_pass` and
   `test_eval_reports_provider_errors_and_stops_early`):
   - cases whose baseline errored no longer count towards n (QE-007);
   - the provider's error type and message are recorded and shown;
   - a run stops after 10 consecutive errors.

   No tokens were billed for the rejected calls.
2. **The model rejects `temperature`.** The second attempt stopped after 10 calls with
   "`temperature` is deprecated for this model". Since QE-012 required temperature 0, the
   requirement was changed through **SCR-001**: `--temperature default` sends no temperature,
   in both arms, and the report states it (commit 8bcd86e).

The invalid record written by the first two attempts was never committed.

## Tests and evidence

- **Local** (Windows, CPython 3.11): `pytest tests` → **488 passed, 9 skipped** (browser and
  packaging, run in CI). `ruff`, `mypy --strict` and `lint-imports` are clean (5 contracts; the
  layers contract now has `tokli.http | tokli.eval` as independent siblings).
- **CI:** runs 37111122620 (58fd72c) and 37111165162 (6d5a64b): all 9 jobs green. Run 37118616732
  (6100118, the final commit with the real record and the strict CC-020): all 9 jobs green.
- **RED first:** 24 tests failed against interface stubs.
  - Two tests had passed vacuously and were tightened (the header test, the CC-020 test
    checked against the old provisional record).
  - The progress-line test was written together with the feature, not before it.
  - Both regression tests and the SCR-001 tests were seen failing first.
- **Cases:** `evals/cases/`, 44 files (22 per family) from `evals/make_cases.py` (fixed seeds).
  The lint passes, with no developer paths or key patterns. Every case is exercised by
  `json_minify` (0 `not_exercised`).
- **Traceability:** rows for QE-001, QE-004, QE-005, QE-007, QE-009…QE-012 and QE-016…QE-020.

## Architecture changes

- **New package `tokli.eval`:** `cases`, `checkers`, `verdict`, `record`, `runner`, `command`.
  The CLI subcommand is `tokli eval smoke`.
- **ADR 0008:**
  - the package's layering, as a sibling of HTTP;
  - the credential rule: the key comes only from the variable named by `--api-key-env`;
  - what is committed (records and reports, not `cases.jsonl`).
- **Reading of QE-017:** a byte-identity compressor can never change a request, so every case
  would be `not_exercised` (QE-012) and the self-test could never reach a verdict. The
  self-test's "identity" therefore re-indents the JSON: every value is kept and the bytes change.

## Observability evidence

- **No proxy path, telemetry row or trace is touched by an eval run.** The import contract and
  `test_eval_never_auto_starts` check this.
- **The key never reaches output or files:** `test_eval_never_writes_the_key` checks it, and a
  scan of the real run's record, report and per-case file found no key pattern.
- **Results carry outcomes, tokens with methods, provider error types and messages, and
  provenance** (QE-005, QE-014).

## Known limitations

- **Calls run one at a time:** the real run took about half an hour on Opus.
- **No temperature control** for models that reject the parameter. The majority of 3
  repetitions absorbs the variation; the report states the setting.
- **One model, one provider:** the smoke tier detects gross damage only. The full tier (S8)
  brings scale and confidence intervals.
- **Security note:** an API key was pasted into the chat several times during the live runs. The
  product owner was asked to revoke it. Claude never used a key from the chat; the runs read it
  from a variable set in the product owner's terminal.

## Unresolved questions

1. **Merge:** squash-merge `s2.5-smoke-eval` into `main` after acceptance, as before.
   Recommendation: yes.

Gate 2 record: **accepted 2026-10-03**, the human's words: "accetto S2.5". The merge follows the
recommendation (squash-merge into `main`), under the product owner's standing statement that they
accept Claude's proposals.
