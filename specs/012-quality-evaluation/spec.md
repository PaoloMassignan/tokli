# SPEC 012 — Quality evaluation

Status: Draft (revised in Phase 0.1) · Slices: **S2.5 (smoke tier: minimal harness, case/record formats, cost controls)**, S8 (full tier) · Related: TOKLI_TEST_STRATEGY §5, §7, PHASE0_1_REVIEW.md
Approved for S1 (2026-09-30): QE-016 `provisional` record for `json_minify` only.

## Purpose
Decide with evidence whether a compressor may be enabled by default, and publish its quality
effect alongside its savings.

Evaluation checks **assumptions** (SPEC 009 claim type ASSUMPTION), never mechanical guarantees:
those are proven by Tier 0 tests. It comes in two tiers that share one case format and one record
format:

| Tier | Slice | Question it answers | Detects |
|---|---|---|---|
| **Smoke** | S2.5 | "Does this compressor save tokens without measurably damaging the task?" | gross damage only (see QE-015) |
| **Full** (Tier 2 + Tier 3) | S8 | Non-inferiority with confidence intervals, across models and providers, plus agent tasks | small effects |

## Rationale
- A metric that normalises away what a compressor removes (for example token F1 that ignores articles) cannot judge that compressor.
- A quality figure always comes from a real run. The harness never reports a constant or fabricated score.
- Fact probes on agent-shaped content (JSON, logs, diffs, grep) need many cases per category, not one.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 012 rows).

## Requirements

| ID | EARS requirement |
|---|---|
| QE-001 | THE evaluation harness SHALL compare, for each case, the baseline request and the Tokli-compressed request built by the **real pipeline** (not by calling a compressor directly), with the same model, parameters and seed. |
| QE-002 | THE harness SHALL report per compressor and content category: n, token saving (estimate and exact from usage), accuracy baseline/compressed, paired delta with a 95 % paired-bootstrap CI, latency overhead, and error/refusal rate. |
| QE-003 | THE **full** tier SHALL run each category with ≥ 40 cases, on ≥ 2 models from ≥ 2 providers, and ≥ 3 repetitions at temperature 0. |
| QE-004 | THE harness SHALL score with deterministic, category-specific checkers (exact value extraction, set equality) and SHALL NOT use metrics that normalise away the content a compressor removes. |
| QE-005 | THE harness SHALL store for every run: Tokli version, config hash, fingerprint, model ids, dates, generator seed, and per-case raw outputs in a results directory excluded from the package. |
| QE-006 | WHEN a compressor is default-enabled in a **v1 release**, THE release checklist SHALL include a full-tier (Tier 2) report meeting the thresholds in TOKLI_TEST_STRATEGY §5, and for tool-result compressors a Tier 3 report on tool-call failure rate. Before v1, a smoke-tier record suffices for a default (CC-020, QE-016). |
| QE-007 | THE harness SHALL NOT report a quality figure when fewer than the required cases succeeded. It SHALL report "insufficient data". |
| QE-008 | THE harness SHALL measure isolated savings (each compressor alone) and chained savings (registry order) on the same corpus. |
| QE-009 | WHEN the user starts `tokli eval`, THE SYSTEM SHALL display the planned cases, models, repetitions and an estimated cost (from the price book, labelled as an estimate), and SHALL proceed only after interactive confirmation or when `--max-cost <amount>` is given. |
| QE-010 | WHILE an evaluation runs, THE SYSTEM SHALL track the cost from provider usage and SHALL stop before the next call that would exceed the confirmed estimate × 1.2 or `--max-cost`, reporting partial results as "insufficient data" where QE-007 applies. |
| QE-011 | THE SYSTEM SHALL NOT start an evaluation automatically, on a schedule, or from the proxy request path. IF pricing for a chosen model is unavailable, THEN THE SYSTEM SHALL require `--max-calls` instead of a cost cap. |

QE-001, QE-004, QE-005, QE-007 and QE-009…QE-011 apply to **both tiers from S2.5**.

### Smoke tier (S2.5)

| ID | EARS requirement |
|---|---|
| QE-012 | WHEN the user runs `tokli eval smoke --compressor <id> --model <model>`, THE SYSTEM SHALL run every case of every case family that matches one of the compressor's declared `assumptions` in two arms: **baseline** (all compressors disabled) and **candidate** (only `<id>` enabled, same policy LOSSY_ALLOWED so eligibility never interferes). Both arms use the real pipeline, the same model and parameters, temperature 0, and `--repetitions` (default 3). |
| QE-013 | A case SHALL be a versioned file under `evals/cases/<family>/` holding a synthetic, protocol-shaped request body, the task, a deterministic checker id and the expected answer. Each family SHALL name the assumption id it tests. Cases SHALL contain no real prompts, paths or keys. |
| QE-014 | FOR every smoke run, THE SYSTEM SHALL record: Tokli version, both arms' `config_hash`, compressor id and version, model id, date, case-set version, per case and repetition the outcome (`pass`/`fail`/`error`), forwarded input tokens per arm (exact from provider usage, else estimate, labelled), the estimated token saving, and the compressor's `ms_total`. |
| QE-015 | THE smoke verdict per assumption family SHALL be computed as follows. A case passes in an arm when a majority of its repetitions pass. `b` = cases passing in baseline and failing in candidate, and `c` = the reverse. With n ≥ `smoke_min_cases` (default 20) completed cases, the verdict SHALL be `no_measurable_damage` iff `b − c ≤ 1` and candidate errors do not exceed baseline errors by more than 1. Otherwise it SHALL be `damage_detected`. With fewer cases it SHALL be `insufficient_data`. The report SHALL state that the tier detects only gross damage. |
| QE-016 | THE SYSTEM SHALL store the outcome as an evaluation record `evals/records/<compressor_id>.yaml` with fields `compressor`, `version`, `tier` (`smoke`, `full` or `provisional`), `assumptions_covered`, `verdict`, `model`, `date`, `report`. A `provisional` record SHALL be allowed only for `json_minify` and only until the S2.5 exit. The release checklist SHALL reject any `provisional` record, and a smoke record for a v1 default (QE-006). A version bump of the compressor SHALL invalidate its record. |
| QE-017 | THE smoke harness SHALL have a CI self-test against a fake upstream with no provider calls: the identity compressor yields `no_measurable_damage`, and a destructive fake compressor yields `damage_detected`. |

Initial case families (S2.5 builds the first two; S4 adds the next two):

| Family | Assumption | Task shape | Checker |
|---|---|---|---|
| `json_fact_lookup` | `reads_minified_json` | Answer a value lookup over a JSON tool result | exact value |
| `json_verbatim_quote` | `not_quoted_verbatim` (json_minify) | Reproduce a nested JSON fragment for a tool argument | structural equality |
| `reference_fact_lookup` | `resolves_result_reference` | Multi-turn tool history in which the later read is stubbed. Question about the later read. | exact value |
| `reference_verbatim_quote` | `quotes_from_reference_target` | Produce an edit anchor (exact substring) from a file whose later read is stubbed | exact substring of the file |

Extension into S8: the full tier adds case generators (≥ 40 per category), paired-bootstrap CIs,
multiple models and providers, and Tier 3 agent tasks. It reuses the case and record formats,
and the same runner and cost controls.

## Categories (initial)
JSON tool output · grep/ripgrep output (POSIX + Windows) · unified diffs · application logs ·
directory listings (`ls -la`, PowerShell `Get-ChildItem`) · stack traces · prose tool output
(web fetch) · mixed tool result with `<system-reminder>`.

## Tier 3 agent protocol (summary)
20 small tasks on a pinned fixture repository (bug fix, refactor, add test, rename), run with
Claude Code and Codex, Tokli pass-through vs candidate config, 2 runs each. Metrics: task success
(tests pass), number of turns, tool-call failures by type (Edit `old_string` not found, JSON
argument errors), provider-reported input tokens (exact) and estimated cost.

## Acceptance criteria
- AC-QE-1: the harness refuses to emit a delta with n < 40 (QE-007).
- AC-QE-2: a self-test with a deliberately destructive fake compressor (drops every digit) yields a significant negative delta. With the identity compressor it yields a CI containing 0.
- AC-QE-3: the report includes all QE-002 fields and provenance (QE-005).
- AC-QE-5 (QE-012/015): with a fake upstream whose scripted answers differ between arms on exactly 2 of 20 cases (b = 2, c = 0), the verdict is `damage_detected`. With b = 1 it is `no_measurable_damage`. With 19 completed cases it is `insufficient_data`.
- AC-QE-6 (QE-013): a lint over `evals/cases/` rejects a case without an assumption id or checker, and a case containing canary-pattern paths or key prefixes.
- AC-QE-7 (QE-016): a `provisional` record for any compressor other than `json_minify` fails the contract test. After a compressor version bump, its record no longer satisfies CC-020.
- AC-QE-4: without confirmation or `--max-cost` no provider call is made. With a fake provider whose usage exceeds the cap mid-run, the run stops before the offending call. No code path in `tokli.http` imports the eval package.

## Test scenarios
`test_harness_uses_real_pipeline` · `test_harness_insufficient_data` · `test_harness_detects_destructive_compressor` ·
`test_harness_identity_ci_contains_zero` · `test_harness_report_provenance` ·
`test_eval_requires_confirmation_or_max_cost` · `test_eval_stops_at_cost_cap` ·
`test_eval_never_auto_starts` · `test_eval_requires_max_calls_without_pricing` ·
`test_smoke_arms_differ_only_in_candidate` · `test_smoke_verdict_rule` · `test_smoke_insufficient_data` ·
`test_eval_cases_lint` · `test_eval_record_schema_and_provisional_rule` · `test_eval_record_invalidated_by_version_bump` ·
`test_smoke_harness_self_test`

## Open questions
- ~~Q11~~ Resolved: the evaluation budget is the Tokli user's decision per run (QE-009…QE-011).
- Q12: Can a small set of real, consented, scrubbed agent transcripts be used for Tier 2 realism?
