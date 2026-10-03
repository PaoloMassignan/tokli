# S2 — Completion report

Slice: **S2 — Exact usage and honest numbers (Anthropic)**. Branch `s2-usage-calibration`.
Gate 1: approved 2026-10-02 ("Approvo s2"), see `SPEC_REVIEW.md`.

## Requirements implemented

| Spec | Requirements |
|---|---|
| 002 proxy | PX-014 (`accept-encoding: identity` on `POST /v1/messages` only) |
| 003 Anthropic | AN-005, AN-006, AN-007 (with `usage_unavailable(<why>)`), AN-009 (stream and body), AN-010 (`provider_partial`); Q3 resolved by E4 |
| 008 tokens | TM-003, TM-004 (whole-request estimate without binary payloads, off the latency path), TM-005 (method on every figure), TM-009 (outlier and unavailable reasons, one WARNING per minute) |
| 009 compression core | CC-024 (result cache, 64 MB default, `0` = off) |
| 013 telemetry | TC-001 usage, `k` and whole-request estimate fields filled; TC-012 schema v2 with forward migration (ADR 0005) |
| 014 observability | OB-011 calibration check, OB-012 header names persisted, OB-013 rotating log file |
| 017 configuration | `limits.usage_parser_buffer`, `compression.result_cache_mb`, `observability.log_file` |

**Deferred, as approved:** cost (S6), metrics API (S3), OpenAI protocols (S5/S7), Q4
`count_tokens` compression (not scheduled).

## Tests and evidence

- **Local** (Windows, CPython 3.11): `pytest tests` → **402 passed, 7 skipped**. The skipped tests
  need the real tokenizer files or packaging and run in CI. `ruff check`, `ruff format --check`,
  `mypy --strict` and `lint-imports` (4 contracts kept) are clean.
- **CI:**
  - run 37046653118 (commit 18ec305): all 9 jobs green, cross-job identity check green;
  - run 37073342005 (commit 36246a5): 8 of 9 green; ubuntu / Python 3.11 failed on a race in
    `test_usage_unavailable_reasons_end_to_end` (see "Process notes");
  - run 37074372545 (commit cb3ba30, the test made deterministic): **all 9 jobs green**, cross-job
    identity check green.
- **RED first:** with interface stubs in place, 50 tests failed on missing behaviour (missing
  config keys, `None` usage, no calibration, no cache, no log file, schema v1). One exception:
  `test_counter_safe_across_threads` passed before the lock was added, because the race it guards
  against is not reproducible on demand. It stays as a guard.
- **New fixtures** (synthetic, canary only): `tests/compat/fixtures/anthropic_responses/`, six
  files, shapes confirmed or corrected by E4.
- **Traceability:** `TOKLI_TRACEABILITY.md` rows for every S2 requirement point to their tests.

## Live test (E4 and the roadmap exit), 2026-10-02/03

Run on the developer's machine against the real API. The product owner asked Claude to complete
it ("puoi finire tu il live test?"). Claude ran two Claude Code prompts in print mode with the
product owner's existing login. The product owner ran the API-key request themselves with a
helper script, so the key never passed through Claude. Only metadata was read from the database
and the log file.

| Check | Result |
|---|---|
| Streamed Claude Code requests (OAuth), 7 in total | all `usage_source: provider`, exact categories (for example input 2, cache_read 80,130, cache_write_5m 243, output 54) |
| `k` on Claude Code requests | **1.21–1.59**, mostly ≈ 1.49–1.59 (in range) |
| Rate-limited request (429) | `usage_unavailable(upstream_status)`, relayed unchanged |
| Non-streaming request with a pretty-printed JSON tool result (API key, `claude-haiku-4-5`) | `outcome: compressed`; usage input 2,777 (exact); estimated saving 1,637 → **calibrated 2,108** (`k` = 1.287); whole-request estimate 3,794 → 2,157 |
| Tokli overhead | 0.6 ms (curl request), 1.3–4.5 ms (Claude Code requests) |
| Header names persisted | yes, names only (for example `anthropic-version`, `x-api-key`) |
| Log file | written to `<data dir>/logs/tokli.log`, JSON lines |

**E4 findings (SPEC 003, Q3 resolved):**
- every `message_delta.usage` repeats the input and cache totals cumulatively;
- it adds `iterations` and `output_tokens_details`, which Tokli does not use;
- it does **not** repeat the `cache_creation` 5m/1h split.

This exposed a bug: the parser applied the "no split → all 5m" fallback to the delta and overwrote
the split read from `message_start`. Fix: regression test
`test_message_delta_without_split_keeps_cache_split_from_message_start` first (failed: 1,200 / 0
instead of 1,000 / 200), then the fix (commit 36246a5). The live data had no 1h writes, so no
recorded figure was wrong. The error-event case stays fixture-based, because it cannot be
triggered on purpose.

**Roadmap exit:** the trace shows exact forwarded usage for streamed Claude Code requests and a
calibrated saving with method labels. In those sessions the saving itself is 0, because
`json_minify` has nothing to do: `Read` and `Bash` are verbatim tools. The non-zero calibrated
saving was shown live with the curl request.

## Architecture changes

- **New modules:**
  - `tokli.domain.usage` (`Usage`);
  - `tokli.protocols.anthropic_usage` (stream and body parsers);
  - `tokli.tokens.calibration` (`calibrate`, `OutlierWindow`);
  - `tokli.app.measurement` (whole-request estimate and calibration for one request).
- **Changed modules:**
  - `tokli.compression.engine`: `ResultCache` (CC-024);
  - `tokli.telemetry.store`: schema v2, migration;
  - `tokli.observability.logs`: `SafeRotatingFileHandler`;
  - `tokli.http.proxy`: usage tee, estimate in a worker thread, completion after the estimate.
- **Import contracts:** unchanged and kept. HTTP reaches tokens and protocols only through
  `tokli.app`. **No new seam:** the parsers and the cache are concrete.
- **ADR 0005:** schema v2 and the first forward migration.
- **`TokenCounter` is now thread-safe.** A lock guards its cache; tokenisation runs outside the
  lock.
- **`config_hash` default changed:** the two new keys sit in hashed sections (CF-006), so S1 and
  S2 records have different default hashes.

## Measured performance (TOKLI_TEST_STRATEGY §8; reported, not gated)

E9 on the CI runners, p95 in ms. Commit 18ec305; the cold baseline was committed in S1.

| OS | 200k cold | 200k warm (cache on) | 200k warm (cache off) | 200k estimate (off path) | 50k warm |
|---|---|---|---|---|---|
| Linux | 113.3 (1.00× baseline) | **12.1** (S1: 53.0) | 43.9 | 4.5 cold / 2.3 warm | 3.1 |
| macOS | 167.3 (0.82×) | 56.9 (S1: 110.2) | 69.4 | 12.0 / 3.8 | 16.6 |
| Windows | 145.5 (**1.43×, warn**) | 33.1 (S1: 54.9) | 73.2 | 6.5 / 3.1 | 4.3 |

- **The result cache works on the common case.** A conversation resent with one new turn is now
  under the Vision target (25 ms) at 200k on Linux and locally on Windows (13.7 ms). It is not yet
  under the target on the macOS and Windows runners.
- **Windows cold "warn"** (1.4–1.8× against the S1 baseline): Linux shows 1.00× with the same
  code. A local A/B on Windows shows no cold cost from the cache (200k cold: 84 ms with the cache,
  91 ms without). The likely cause is runner variance. The baseline is unchanged (I6), and the
  weekly performance job keeps watching it.
- Requests that are entirely new ("cold") remain above the target, as in S1.

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] **New code paths emit spans.** `usage` carries source, reason, categories, SSE event counts,
  `delta_usage_fields` and parse time. `calibrate` carries `k`, estimate, saving, method and the
  estimate's duration.
- [x] **New decisions use closed-set codes:** `usage_unavailable(<why>)`, `calibration_outlier`,
  `calibration_unavailable`. The set was extended at Gate 1 (P7).
- [x] **New telemetry fields are in the schema (v2), the API view and the retention job.** The
  retention job deletes whole rows.
- [x] **Credential and content scans cover the new paths:**
  `test_response_content_never_recorded` (trace, log, DB, with a streamed canary response) and
  `test_log_file_contains_no_credentials_or_content`.
- [x] **The request view shows usage, `k`, `saving` and `request_tokens_original` with methods.**
  The summary log line carries usage, the saving with its method, `k` and the SSE metadata.

## Known limitations

- **`k` on Claude Code traffic is ≈ 1.5:** the proxy tokenizer and the provider's hidden tool
  prompt. It is in range, but at around 1.6 it is not far from the 2.0 outlier bound. E3 (per-model
  expectation) is the place to revisit the range.
- **SSE metadata survives a restart only in the log file.** Traces are in memory; the database
  keeps usage and `k`, not event counts.
- **An unreachable or timed-out upstream records `usage_unavailable(upstream_status)`.** The
  closed set has no separate code for it.
- **The result-cache bound is approximate:** output characters plus a fixed overhead per entry.
- **The outlier window lives in memory** and starts empty after a restart.
- **Observation, not a Tokli finding:** in the live curl request the model miscounted (40 items
  marked ok; the synthetic data has 53). `json_minify` is lossless with structural equivalence,
  proven by the round-trip properties, so the content the model received was equivalent. Answer
  quality is measured by the evaluation tiers (S2.5), not here.

## Process notes

- **Test bugs found during GREEN** were fixed in the tests, without weakening any assertion:
  - a fake tokenizer spec without a split pattern;
  - a span status read from the attributes;
  - an invariant test whose protected text also appeared elsewhere.
- **Flaky CI test** `test_usage_unavailable_reasons_end_to_end`: a gate released after the client
  disconnect let the upstream finish first on a fast runner. Fixed by an upstream that never ends
  on its own (commit cb3ba30), with the same assertion.
- **An API key was pasted twice into the chat** during the live test. It was not used. The
  product owner was asked to revoke it. The helper script `C:\temp\tokli-live-test\curl_test.cmd`
  (outside the repository) reads the key interactively and stores nothing.

## Unresolved questions

1. **Range of `k`:** keep [0.5, 2.0] for now? Recommendation: yes. Collect the dogfood
   distribution from S3, then decide with E3.
2. **Merge:** squash-merge `s2-usage-calibration` into `main` after acceptance, as for S1.
   Recommendation: yes.

Gate 2 record: **accepted 2026-10-03**, the human's words: "accetto S2". The unresolved
questions follow the recommendations, under the product owner's standing statement that they
accept Claude's proposals: the `k` range stays [0.5, 2.0] until the S3 dogfood data, and the branch
is squash-merged into `main`.
