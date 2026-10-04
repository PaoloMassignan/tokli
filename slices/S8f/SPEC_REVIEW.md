# S8f — Spec review

- **Slice scope (TOKLI_ROADMAP.md, S8f):** the request budget keeps history stable.
- **Specs and requirements in scope:** SPEC 009 CC-014 as changed by S8f SCR-001, and AC-CC-15.
- **Out of scope:**
  - the pipeline's per-stage limit (PL-005, 1000 ms), see Unresolved questions in the
    completion report;
  - any change to compressor outputs.

The slice is a single approved SCR (`SCR-001-budget-keeps-history-stable.md`), which holds the
evidence, the exact EARS text and the test plan. This review records only what the SCR leaves
open.

## 1. Ambiguities

- **CC-014 "cached skip" and the CC-024 statistics.** A repeated skip is a cache hit. Proposed
  reading: it counts in `cache_hits` and in `skipped_budget`, with reason `budget_exhausted`.
  CC-024 asks for stats "exactly as if computed", and a fresh skip records `budget_exhausted`.

## 2. Contradictions

None found.

## 3. Missing behaviour

None. With the cache off (`result_cache_mb: 0`) nothing records a decision. The behaviour then
is the old CC-014 for segment-scope compressors; the SCR states this.

## 4. Portability concerns

None. The tests use an injected clock, never wall time.

## 5. Observability requirements

- **Unchanged:** the skip reason `budget_exhausted` and `skipped_budget` (UI-009).
- **What changes:** pruners never report `budget_exhausted` any more.

## 6. Architectural risks

- **No new seam.** The result cache stores one extra kind of entry, an engine-private sentinel.
- **No ADR.** No contract shared by more than one module changes.

## 7. Product questions

None; the SCR was approved as written.

## 8. Implementation decisions

- **Sentinel.** The skip is stored as an engine-private `Applicability` sentinel. It is not part
  of the compressor contract.
- **Cache lookup comes first.** The lookup now happens before the budget check. On a miss, the
  budget check runs before any compressor call.
- **Unused parameter removed.** The request-scope loop no longer reads the request start time,
  so its parameter is removed.

## 9. Test plan

| AC | Test |
|---|---|
| AC-CC-15 (a) | `test_budget_never_skips_pruners` |
| AC-CC-15 (b) | `test_budget_applies_cached_results` |
| AC-CC-15 (c) | `test_budget_skip_is_sticky` |
| AC-CC-15 (d) | `test_budget_keeps_history_stable` (integration, fake clock, 12 requests) |
| CC-014, cache off | `test_budget_without_cache_still_skips` |
| CC-014, `cost_class: cheap` | `test_request_scope_compressors_are_cheap` (contract) |
| AC-CC-8 (unchanged) | `test_budget_exhaustion_skips` |

The S8c and S8e integration tests no longer lift the budget. They now guard the flake found in
CI run 37228678522.

## Gate 1 record

- **Date:** 2026-10-04.
- **The human's words:** "approvo SCR". The SCR states that its approval counts as Gate 1.
- **Spec delta:** SPEC 009 CC-014 and AC-CC-15, plus the "Router budget" row of
  TOKLI_TEST_STRATEGY §8, in the S8f commit.
