# S8a-1 — Completion report

Sub-slice: **S8a-1 — `search_group`, `log_filter`, the verbatim opt-in**. Branch
`s8a-claude-compressors`.
- **Gate 1:** approved 2026-10-03 ("Accetto"), see `SPEC_REVIEW.md` §11.
- **Spec changes:**
  - SCR-001 (per-compressor verbatim opt-in; approved at Gate 1);
  - SCR-002 (unexercised families stay out of the verdict; approved 2026-10-04, "approvo SCR-002").

## Requirements implemented

| Spec | Requirements |
|---|---|
| 010 | `search_group` CP-SG-001…004 (review A8, reason codes `too_few_grep_lines`, `no_group`); `log_filter` CP-LF-001…004 (review A6, reason codes `too_few_leveled_lines`, `nothing_omitted`); both off by default |
| 009 | CC-021 after SCR-001 (opt-in); CC-015 for SELECTIVE compressors (a contract test now checks that every guarantee names an existing test) |
| 011 | RT-001: `grep_lines`, `leveled_ratio`, `line_count`, `crlf` |
| 012 | families `grep_fact_lookup`, `grep_verbatim_quote`, `log_fact_lookup`, `log_verbatim_quote` (22 cases each, case set `2026-10-03.2`); QE-015 after SCR-002 |
| 016 | UI-012: the "Also on Read, Bash, …" toggle with its warning |
| 017 | CF-009 after SCR-001; the six keys of "Keys added in S8a-1" |

**Deferred, as approved:** S8a-2 (`diff_context_trim`, `dictionary`), S8a-3 (pruning of superseded reads), S8b.

## Exit criteria

1. **Tier 0 tests green:** yes (below).
2. **Smoke records for both compressors, run by the human:** done on 2026-10-04 (below).
   Both are `no_measurable_damage`.
3. **Savings measured on dogfood:** measured offline on the human's recent Claude Code sessions (next section).

## Measured saving (offline, on the human's sessions, 2026-10-04)

**Method:**
- The real compressors with default options ran locally over every tool result of the 39 sessions of E5b-lite (last 14 days), with consent.
- Only token totals were printed.
- Tokens are characters / 4.
- Weights count how many later requests resend a result, stopping at compaction.
- The engine's gate is simplified: ≥ 64 tokens and a gain ≥ max(4, 1 %).
- The run assumes the opt-in is on, so `Bash` and `Read` are included.

Re-measured after S8a SCR-003. The first measurement counted log timestamps grouped as fake
grep paths; it gave 0.74 % for `search_group` and 1.55 % for both.

| Tool | Volume (results ≥ 64 tokens) | `search_group` v2 saves | `log_filter` saves | Both |
|---|---|---|---|---|
| `Bash` | 517.3 M | 4.7 M (126 results) | 3.4 M (49) | 8.1 M (1.6 %) |
| `Read` | 418.3 M | 0 | 5.4 M (12, log files) | 5.4 M (1.3 %) |
| `Grep` | 19.0 M | 1.0 M (25) | 0 | 1.0 M |
| Others | | 0.0 M | 0.5 M | |
| **All tool results (1,127.0 M)** | | **0.51 %** | **0.83 %** | **1.34 %** |

**Without the opt-in** (the default), the reach is `Grep`, `PowerShell` and agent output: about 0.2 % of the tool-result volume.

**Reading:**
- `Bash` and `Read` are 84 % of the volume, but only about a tenth of `Bash` output has grep shape and a tenth log shape.
- Even on those, the compressors remove only the repeated paths and the repeated routine lines.
- `Read` is mostly source code, which no safe transformation shrinks.
- The tokens are mostly provider cache reads (about 10 % of the input price), so the monetary saving is smaller than the token saving.

## The first smoke run and S8a SCR-003 (2026-10-04)

- **The run:** `eval_s8a1.cmd`, run by the human. Only `search_group` produced a result:
  `insufficient_data`, stopped by the call cap at 300 calls.
  - `grep_fact_lookup`: 18 complete cases, b = 0, c = 0.
  - The other families: no complete case.
- **Cause:** the definition of a grep line accepted log timestamps (`2026-10-03 09:00:01` →
  path `2026-10-03 09`). `search_group` therefore exercised the log family too, which needed 396
  calls.
- **Fix:** S8a SCR-003, approved. A grep path has no whitespace and contains `/`, `\` or `.`;
  `search_group` goes to v2.
- **Tests, written first and failing for this reason:**
  - `test_search_group_ignores_timestamps`;
  - `test_grep_feature_ignores_timestamps`;
  - the restored case `time 10:30:00` in `test_search_group_ignores_non_grep_lines`;
  - `test_s8a1_cases_do_not_exercise_the_other_compressor`.
- **This was mine to catch:** the ambiguity was visible during RED, when that case was dropped
  instead of raised.
- **`log_filter`:** its run left no result. The human does not remember the screen (the script
  clears it), so the cause is unknown. A new script runs the two evaluations separately.
- **Superseded record:** `evals/records/search_group.yaml` (v1, `insufficient_data`) is replaced
  by the new run, and its report stays as evidence.

## Smoke evaluations (2026-10-04, `claude-opus-5-5`, model-default temperature, 3 repetitions)

Run by the human with `eval_s8a1_search_group.cmd` and `eval_s8a1_log_filter.cmd`: 264 calls each.

| Compressor | Family | n | b | c | Errors (base / cand.) | Verdict |
|---|---|---|---|---|---|---|
| `search_group` v2 | `grep_fact_lookup` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `search_group` v2 | `grep_verbatim_quote` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `log_filter` v1 | `log_fact_lookup` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `log_filter` v1 | `log_verbatim_quote` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |

- **Families that do not apply** (`json_verbatim_quote`, and the other compressor's quote family)
  are `not_exercised` and made no call (SCR-002, SCR-003).
- **Records:** `evals/records/search_group.yaml` and `evals/records/log_filter.yaml`. The
  reports are in `evals/results/2026-10-04-<id>-claude-opus-5-5/report.md`.
- **The saving on these cases is not representative.**
  - Exact provider usage: `search_group` −10.3 %, `log_filter` −80.1 % of the forwarded input.
  - The case logs are built to be very repetitive, so they say nothing about real traffic. The
    real-traffic figure is the offline measurement above.
- **The first `search_group` run (v1, before SCR-003) is superseded.** Its report was
  overwritten by the v2 run in the same folder; the v1 version is in the git history
  (commit 2566569).
- **What these records mean.** They only allow a default: neither compressor is on by default.
  `log_filter` is SELECTIVE and never default-on in v1, and `search_group` stays off by this
  slice's decision (SPEC 017). They do not cover `Bash` output with the opt-in (E8, S8b).

## Tests and evidence

- **Local** (Windows, CPython 3.11): `pytest tests` → **654 passed, 10 skipped** (after SCR-003). The browser tests with `RUN_BROWSER_TESTS=1` (Chromium in the session's scratch folder) → **14 passed**. `ruff`, `mypy --strict` (72 files) and `lint-imports` (5 contracts) are clean.
- **CI:** run 37183367938 (commit 0576f6d).
  - **First attempt:** 8 of 9 jobs green. Windows / Python 3.13 failed one test,
    `test_every_api_token_field_has_method`: the first request of a fresh Tokli had no engine
    report.
  - **Re-run of the failed job:** green. All 9 jobs green, and the cross-job identity check
    green. Ubuntu/3.12: 13 browser tests passed.
  - **Not seen before** in the 25 previous CI runs, and not reproduced.
  - **Probable cause:** a pipeline stage over its 1,000 ms budget (`stage_timeout`) on a stalled
    runner. The cause is **not proven**.
  - **Follow-up:** the test now prints the trace's decisions when it fails, so a recurrence
    shows the reason.
- **CI, final:** run 37186898143 (commit ca1c170, after SCR-003 and the test fix): all 9 jobs green at the first attempt; cross-job identity check green.
- **RED first.** 40 new tests failed on behavioural assertions before the code; none failed on an import or name error. The compressor modules first existed as skeletons with their `SPEC`. Exceptions:
  - `test_verbatim_opt_in_does_not_cover_unresolved_tools` passed before the code: CC-023 is unchanged, and the test guards it.
  - `test_assumption_without_exercised_family_is_insufficient` (SCR-002) passed before the code: today every empty family already gives `insufficient_data`.
- **Tests changed because the spec changed:**
  - **Key and feature lists:**
    - `test_keys_marked_ui_editable` (CF-009, SCR-001);
    - the config-loader key tables and the pinned default `config_hash`;
    - `test_routing_inputs_closed_and_no_ml` (RT-001 features);
    - `test_chain_order_by_stage_then_id` (registry);
    - `test_registry_lists_the_s8a1_compressors`, replacing the S4 one.
  - **Loaded families:** `test_cases_load_by_assumption`, for the families loaded for `not_quoted_verbatim` (QE-012).
  - **SCR-002:** four `test_eval.py` tests. They now assert which families are unexercised and count calls on exercised cases only: stricter, not weaker.
  - **Doctor goldens:** both regenerated deliberately. The diff holds only the new hash and the new keys and compressors.
  - No assertion was weakened, skipped or deleted.

## Intermittent CI failures (both on Windows / Python 3.13)

1. **`test_every_api_token_field_has_method`:** run 37183367938, not reproduced on re-run. It
   is described under "Tests and evidence".
2. **`test_overhead_percentiles_by_bucket`:** run 37186486041. The test wrote 75 requests and
   read back 11.
   - **Cause:** since S4.5 D4, `close()` stops waiting for a busy writer after 10 s, and on that
     runner the SQLite commits were slow enough. The test helper assumed that `close()` means
     everything is written.
   - **Fix (test only):** the helper calls `flush(timeout_s=120)` before `close()`, so it waits
     until the rows are actually there. No assertion changed.
   - **What this shows about the product:** at shutdown on a very slow disk, the last rows can
     still be in flight when `close()` returns. That is the trade-off accepted in S4.5: a bounded
     shutdown, and a writer that never loses its connection.

## Corrections found during the work

1. **SCR-001 §7 was wrong.** It said `config_hash` changes only when a user sets a new key. The
   new keys' defaults are in the hashed `compressors` section, so the default hash changes once
   with the upgrade, as `pruning` did in S4. CF-006 is unchanged; the SCR text is corrected.
2. **SCR-002 §5 was wrong.** It said the four eval tests would pass unchanged. They had to stop
   assuming that every loaded family is exercised; the SCR text is corrected.
3. **The routing features cost time on every request.**
   - A paired local E9 run showed `200k_warm` at 1.44× `main`.
   - The shape counts are now cached per text (LRU of 8,192, as the token counter), which
     brought it back to 0.96×.
   - `test_features_linear_time` clears that cache before each measurement, so it still measures
     the computation.

## Architecture changes

- **New modules:**
  - `tokli.compression.text_shapes`: one definition of grep lines and log levels, shared by the features and the compressors;
  - `tokli.compressors.search_group`;
  - `tokli.compressors.log_filter`.
- **Config:** `SearchGroupOptions` and `LogFilterOptions` in the `compressors` section.
- **Engine and bootstrap:** `EngineSettings.verbatim_opt_in`; the bootstrap derives it from the options.
- **Eval:** `overall_verdict(families, assumptions)`. `assumptions_covered` lists only exercised assumptions, and the provenance lists every case set loaded.
- No new dependency and no persisted-format change. The import contracts are unchanged and green.

## Measured performance (E9, reported, not gated)

**Paired local run**, same machine, one after the other, 15 iterations, p95. The machine was
under load: `main` itself measured 2–3× its earlier figures, so only the ratios mean something.

| Bucket | `main` (202d8dd) | S8a-1 | Ratio |
|---|---|---|---|
| 50k warm | 10.2 ms | 12.4 ms | 1.22× |
| 200k cold | 177.2 ms | 217.0 ms | 1.22× |
| 200k warm | 72.7 ms | 69.4 ms | 0.96× |
| 200k warm, no cache | 99.9 ms | 102.2 ms | 1.02× |

The small buckets swing between runs (10k warm: 1.64× and then 1.84×, on 2–4 ms).

**CI** (run 37183367938 against `main` after S4.5, run 37151545813), p95 of `200k_warm`:

| Runner | `main` | S8a-1 | Ratio |
|---|---|---|---|
| Linux | 37.3 ms | 22.3 ms | 0.60× |
| Windows | 33.0 ms | 39.2 ms | 1.19× |
| macOS | 13.7 ms | 71.1 ms | 5.19× |

On macOS the comparison script reports `FAIL` for 50k and 200k warm.

The three runners contradict each other on the same code (0.60× to 5.19×). This matches the
CI variance recorded in S4.5, where the same code measured 14 ms and 66 ms. The paired local run
above is the comparison to trust. This report does not claim that S8a-1 has no overhead on
macOS: it was not measured there in a paired way.

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] **Decisions use reason codes.** New decisions use the existing `not_applicable(<code>)`
  form with the codes listed in SPEC 010. The verbatim skip keeps `verbatim_tool`.
- [x] **No new spans.** The compressors are timed and recorded by the engine like every
  compressor.
- [x] **No new telemetry fields.** The per-compressor stats rows cover the two compressors
  automatically.
- [x] **Content scans.** The compressors add only the `[file]` headers, `\` escapes and the
  omission note. The integration test checks a canary line kept verbatim by `log_filter`.
- [x] **The UI shows both compressors.** The Settings and Compressors pages, with kind,
  assumptions, "not evaluated" and the opt-in toggle.

## Known limitations

- **Small real saving on Claude Code** (above). The volume that remains is source code (`Read`) and varied command output (`Bash`); reaching it needs lossy transformations outside the v1 catalogue, or E10 (the `Edit`/`Write` arguments).
- **The verbatim-quoting risk on `Bash` with the opt-in is not measured.** The smoke families use non-verbatim tools; E8 (Tier 3) is in S8b.
- **`grep_lines` matches any `name:number:` line**, including compiler and linter output. This is harmless (the grouping is lossless) and it is part of the measured saving.

## Unresolved questions

1. **Default of `search_group`.** It now has a `no_measurable_damage` smoke record, so CC-020
   would allow it on by default. Its real saving is small (0.51 % of the tool-result volume with
   the opt-in, under 0.1 % without), and it changes what the model reads. Recommendation: keep
   it off by default; decide again after S8b (Tier 2 and E8).
2. **Next sub-slice.** Given the measured saving, should S8a-2 and S8a-3 go ahead as planned, or should the next step measure what the remaining `Bash` volume is (by program name, counters only) before choosing?

Gate 2 record: **accepted 2026-10-04**, the human's words: "Accetto S8a-1, accetto le tue proposte".
The unresolved questions follow the recommendations:
- `search_group` stays off by default, to be decided again after S8b;
- the next step is a measurement of the remaining `Bash` volume (counters only) before S8a-2 and S8a-3;
- the branch is squash-merged into `main`.
