# S8f SCR-001 — The request budget must not change history already sent

Status: **approved 2026-10-04** ("approvo SCR"). Applied to SPEC 009 (CC-014, AC-CC-15),
TOKLI_TEST_STRATEGY §8, TOKLI_TRACEABILITY. Raised in the S8e completion report ("A second
intermittent failure, and what it shows about the product").

If approved, the change is carried out as a small slice **S8f** (roadmap entry added on approval).
Approval of this SCR counts as Gate 1 for S8f. Gate 2 stays as usual.

## 1. Affected requirements

- **SPEC 009 CC-014** (approved S1): when the request's time budget
  (`compression.request_budget_ms`, default 50) is exhausted, the remaining compressor
  invocations are skipped with `budget_exhausted`.
- Requirements it undermines without changing them:
  - CC-024 (the result cache makes repeated history cheap);
  - PR-004 and PR-030 (prefix stability of the reference pruners);
  - PR-023 (`edit_args_on_resume` repeats the same replacements between resumes).
- AC-CC-8 is unchanged. `TOKLI_TEST_STRATEGY.md` §8 ("Router budget" row) gets its wording
  updated.

## 2. Evidence

**E1. CI flake, S8e run 37228678522 (macOS / Python 3.11).**
- `test_resume_pruning_stable_between_resumes` failed: at the third request the old `Edit` was
  not stubbed.
- Reproduced locally with a tiny `compression.request_budget_ms`: the pruner was skipped with
  `budget_exhausted`.

**E2. Synthetic probe (2026-10-04, Windows, CPython 3.11, default config).**
- **Conversation:** `benchmarks.overhead.build_request(tokens, salt=0, tail="new turn i")`, the
  E9 "warm" conversation (the same history resent with a new last turn, as an agent does).
- **Method:** each request runs through the bootstrapped pipeline. The table reads the engine
  report's `CompressorStats` (`ms_total`, `accepted`, `skipped_budget`).

| Size | Request | `json_minify` | `reread_by_reference` |
|---|---|---|---|
| 200k | 1, 2, 3 | 19.3 / 0.7 / 0.7 ms, 96 accepted, 0 budget skips | ≈10.4 ms, 95 accepted, 0 skips |
| 400k | 1 | 12.8 ms, **141 accepted, 50 budget skips** | 21.4 ms, 190 accepted |
| 400k | 2 | 13.6 ms, **185 accepted, 6 budget skips** | 21.0 ms, 190 accepted |
| 400k | 3 | 3.0 ms, **191 accepted, 0 budget skips** | 21.4 ms, 190 accepted |

At 400k the three requests carry **the same history**, but `json_minify` compressed 141, 185
and 191 of its segments.

**What this shows:**
1. **The budget makes compression depend on timing, not on content.** A history segment sent
   whole on one request is sent compressed on the next. The forwarded prefix changes, so the
   provider rewrites its cache from that point. Cache writes are 27.5 % of the human's
   measured cost (TOKLI_EVIDENCE, E10 cost map).
2. **It is not limited to the pruners.**
   - **Pruners:** they run first, on the whole request, and are not cached. At 400k,
     `reread_by_reference` alone uses 21 ms of the 50.
   - **Segment-scope compressors:** they come after the pruners, in document order. Whatever
     the pruners leave decides how far down the history they get. Their cached results
     (CC-024) are skipped as well, because the budget is checked before the cache.
3. **The request stays valid and lossless.** The cost is money (cache rewrites) and lost
   saving, not correctness.

**Related, not part of this SCR:**
- The pipeline's per-stage limit (PL-005, fixed at 1000 ms) discards the whole compression
  stage when exceeded. On such a request every segment goes out uncompressed: the same
  problem, on a larger scale.
- It is 20 times the request budget and has not been observed. It is listed under "Unresolved
  questions" of S8f.

## 3. Why the requirement should change

- **What CC-014 is for:** it bounds the latency Tokli adds (E5a: about 1 s per request without a
  bound).
- **Two of its costs can be removed:**
  - **Cached results.** A result already computed for a segment costs a dictionary lookup.
    Skipping it saves no time and changes history.
  - **Pruners.** Their decisions must be the same on every request (PR-004, PR-023, PR-033).
    They are required to be cheap: `cost_class: cheap`, and PR-035 linear for
    `reread_by_reference`.
- **A third cost needs a rule:** a segment skipped on one request must not become compressed
  on a later one only because time was left over. It stays skipped while its decision is cached.
  Later requests repeat the first decision instead of re-deciding it.

## 4. Proposed change

**CC-014** becomes:

> CC-014 | WHEN the request's compression time budget (`compression.request_budget_ms`,
> default 50, a provisional POLICY value until E9 and dogfood data exist) is exhausted, THE
> SYSTEM SHALL skip each remaining segment-scope compressor invocation **that has no entry in
> the result cache (CC-024)**, with reason `budget_exhausted`, count the skips per compressor
> (`skipped_budget`), and SHALL NOT fail the request. **THE SYSTEM SHALL store each such skip in
> the result cache under the invocation's key, and SHALL apply a cached result or a cached skip
> whatever budget remains, so that the decision taken for a segment repeats on later requests
> while it stays cached. THE budget SHALL NOT skip request-scope compressors (SPEC 019), whose
> decisions must be the same on every request; every request-scope compressor SHALL declare
> `cost_class: cheap`.** The budget is a runtime control, not an acceptance criterion for a
> compressor (TOKLI_TEST_STRATEGY §8). (S8f SCR-001.)

**New acceptance criterion:**

> AC-CC-15 (CC-014): with a clock that exhausts the budget part-way, (a) a request-scope
> compressor still runs; (b) a segment compressed on request 1 is compressed identically on
> request 2 even when the budget is exhausted before it; (c) a segment skipped for the budget on
> request 1 is skipped again on request 2 even when budget remains; (d) on a growing
> conversation the forwarded text of every segment already sent is byte-identical from one
> request to the next.

**Consequences:**
- **Lost saving.** With the result cache on, a segment skipped once stays uncompressed until it
  leaves the cache.
- **Cache off.** With `compression.result_cache_mb=0` the cache keeps no decisions: segment
  behaviour is as today, and only the pruner exemption applies.
- **Unbounded pruner time.** Pruner time is no longer bounded by the budget. It stays bounded
  by their complexity requirements, the per-call timeout (CC-008) and the stage limit (PL-005).

**`TOKLI_TEST_STRATEGY.md` §8, "Router budget" row,** last cell becomes:

> the compressor is skipped for that segment (visibly), and the skip is repeated while the
> decision is cached; pruners and cached results are never skipped. Users can change the
> budget.

## 5. Impact on tests

**New tests:**
- `test_budget_never_skips_pruners` (AC-CC-15 a);
- `test_budget_applies_cached_results` (b);
- `test_budget_skip_is_sticky` (c);
- `test_budget_keeps_history_stable` (d). It is an integration test with a fake clock over a
  growing synthetic conversation, and asserts byte-identical forwarded history.
- `test_request_scope_compressors_are_cheap`, a contract test.

**Changed tests:**
- `test_budget_exhaustion_skips` stays. Its fixture uses cache misses.
- The budget lifts added in S8c/S8e tests (`test_resume_pruning.py`,
  `test_reread_by_reference.py`) become unnecessary and are removed. The flake then becomes a
  real regression test.

## 6. Impact on architecture

- **Engine only** (`tokli.compression.engine`):
  - the cache lookup moves before the budget check;
  - the result cache accepts a "skipped for the budget" entry;
  - the request-scope loop drops its budget check.
- No new module, dependency direction or seam. No ADR: the cache contract (CC-024) is used by
  the engine only.

## 7. Compatibility and migration

- **No change to:** persisted schema, config keys or `config_hash`.
- **Compressor versions:** unchanged, because compressor outputs do not change.
- **Telemetry:** `skipped_budget` keeps its meaning (budget skips per compressor), and now also
  counts repeated cached skips.
- **Dashboard (UI-009):** it shows the rate as before.
