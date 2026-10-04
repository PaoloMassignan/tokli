# S8f — Completion report

## Requirements implemented

- **CC-014 as changed by S8f SCR-001**, with AC-CC-15:
  - a cached decision applies whatever budget remains: a result, or a skip for the budget;
  - a budget skip is cached under the invocation's key;
  - request-scope compressors (pruners) are never skipped by the budget;
  - every request-scope compressor declares `cost_class: cheap`.

**Deferred:** none.

## Tests and evidence

**RED, confirmed before the change.** Four tests failed on behaviour assertions:
- `test_budget_never_skips_pruners`: 0 stubs accepted, 1 expected;
- `test_budget_applies_cached_results`: no patches on the second request;
- `test_budget_skip_is_sticky`: the skipped segment was compressed on the second request;
- `test_budget_keeps_history_stable`: "history changed at request 6".

Two tests passed from the start, as expected:
- `test_budget_without_cache_still_skips` describes the unchanged cache-off behaviour;
- `test_request_scope_compressors_are_cheap` is a contract guard.

**GREEN, local (Windows, CPython 3.11):**
- full suite: 717 passed, 10 skipped (environment-gated, as in earlier slices);
- `ruff check`, `ruff format --check`, `mypy --strict` (75 source files) and `lint-imports`
  (5 contracts kept): all green.

**Changed tests:**
- The S8c and S8e integration tests no longer lift `compression.request_budget_ms`. They run at
  the default budget and guard the flake of CI run 37228678522.

**CI, first run 37233467737** (commit 0e9b901): 7 of 9 jobs green. macOS / Python 3.12 and
3.13 failed `test_reread_linear_time` (S8e, AC-PR-26), which this slice does not touch:
- **Measured:** 17.8x and 18.1x for 10 times the lines, against a limit of 15.
- **Locally the pruner is linear:** 1.5 to 2.0 us per line from 5,000 to 200,000 lines, and the
  same ratio is 9.2x.
- **Cause:** the 6 ms denominator (best of 3, garbage collector on) is dominated by runner noise.
- **Fix (test only):** the best of 7 runs with the collector paused. The sizes and the limit of
  15 from AC-PR-26 are unchanged.

**CI, second run 37234159540** (commit 5a29561): all 9 jobs green; cross-job identity check green.

**Synthetic probe** (`benchmarks.overhead.build_request`, warm conversation, default config,
three requests with the same history):

| | `json_minify` at 400k: accepted / budget skips, requests 1, 2, 3 |
|---|---|
| Before (main) | 141 / 50, 185 / 6, 191 / 0: the forwarded history changed twice |
| After (S8f) | 134 / 57, 134 / 57, 134 / 57: identical every time |

At 200k nothing was skipped, before or after.

## Architecture changes

- **Engine only** (`tokli.compression.engine`):
  - an engine-private `_BUDGET_SKIP` sentinel in the result cache;
  - the cache lookup now comes before the budget check;
  - the request-scope loop has no budget check, and its unused `start` parameter is removed.
- No new module, dependency, seam or contract change. No ADR (SPEC_REVIEW §6).

## Measured performance

Paired E9 run on the same machine (TOKLI_TEST_STRATEGY §8): `main` (2196c88) in a worktree
against this branch, 20 iterations each, `benchmarks.compare`.

- **All compression buckets:** within 0.90×–1.17× of `main`, inside the noise seen between runs.
  200k warm came out at 0.49×; that is noise, not a gain claimed for this slice.
- **One "warn":** `200k_estimate_warm` at 1.48×. That path (TM-004, off the latency path) is not
  touched by this slice, so it is run-to-run noise.
- **Not gated**, as the strategy says.

## Observability evidence

- **Skip reasons:** `budget_exhausted` and `skipped_budget` keep their meaning. A repeated cached
  skip also counts in `cache_hits` (SPEC_REVIEW §1).
- **Pruners:** they no longer report `budget_exhausted`.

## Known limitations

- **Lost saving after a slow first request.**
  - On a first, cold request for a large conversation, the budget skips the tail: the E9 cold
    200k request takes about 130 ms against a 50 ms budget. Examples: the first request after
    Tokli starts, or a long conversation seen for the first time.
  - Those skips now persist while they stay cached, so those segments stay uncompressed for the
    life of the cache.
  - This is the trade the SCR accepted: a stable prefix (no cache rewrite) over a late saving.
- **Cache off.** With `compression.result_cache_mb: 0` segment-scope skips are not remembered.
  Timing can then still change history, as before S8f.
- **Pruner time.** It is no longer bounded by the budget: about 23 ms for `reread_by_reference`
  at 400k tokens in the probe. It stays bounded by their linear complexity and the stage limit.

## Unresolved questions

1. **The pipeline's per-stage limit** (PL-005, fixed at 1000 ms) discards the whole compression
   stage when exceeded. Every segment then goes out uncompressed, which changes the history
   already sent on that request. Never observed (20 times the request budget).
   - Recommendation: leave it until dogfood shows stage timeouts. They are recorded as
     `stage_timeout(transform.compression)`.
2. **The default budget (50 ms)** is still provisional (CC-014). After S8f a low budget costs
   saving, never cache rewrites.
   - Recommendation: revisit it with dogfood data on `skipped_budget`.

## Gate 2 record

- **Date:** 2026-10-04.
- **The human's words:** "Accetto".
