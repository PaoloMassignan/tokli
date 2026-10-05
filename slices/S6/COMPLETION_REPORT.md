# S6 — Completion report

## Requirements implemented

| Spec | Requirements |
|---|---|
| SPEC 013 | TC-004 (positional, with proportional and `assumes_uncached` fallbacks), TC-005…TC-009, TC-017 (saving regions, schema v4), TC-018 (shipped and user price books), TC-019 (OAuth basis), TC-020 (caveats) |
| SPEC 015 | API-002 money figures, API-013 (summary, per compressor, per request); API-012 retired |
| SPEC 016 | UI-013: money card, compressor and request money columns |
| SPEC 012 | QE-009…QE-011 with the price book (`--max-cost`); QE-018 restated |
| S6 SCR-001 | CC-019, PR-012, AC-CC-10, AC-CC-16, AC-PR-8, AC-PR-24 |

- **ADR 0014** (accepted at Gate 1): price book and saving regions.

**Deferred:** none.

**E2 against the real provider:** run by the human on 2026-10-05. It passed (+0.198 against
a tolerance of ±0.25).

## How the human's steer was met

The steer was "the saving should be close to the real one, after the cache".

**What Tokli records.** Each request's saving is recorded by where it sat in the forwarded
request: cache read, cache write, uncached.

**How it is priced:**
- at the cache-read price, 0.05× on Claude Opus 5.5 and 0.1× on most models;
- at the cache-write price, 1.25× or 2×;
- at the input price.

**What a saved token costs over a conversation:** one cache write when it first appears, then
a cache read in each later request. The proportional method stays only as a labelled
fallback.

## Tests and evidence

**RED.** 48 tests failed on behavioural assertions against behaviour-free skeletons; 86
already passed.
- **Corrected premise:** `test_saving_in_written_region_end_to_end` first assumed that 5 % of
  cache reads would leave the JSON result uncached. That 5 % overlapped the result. It now uses
  a first request (0 % read), which states the intended case.
- **Retired requirement:** API-012's tests were replaced, because API-012 itself was retired.

**GREEN, local (Windows, CPython 3.11):**
- full suite with browser tests: **780 passed, 9 skipped** (environment-gated, as in earlier
  slices);
- `ruff check`, `ruff format --check`, `mypy --strict` (80 source files) and `lint-imports`
  (7 contracts kept, 2 of them new for `tokli.pricing`): all green.

**CI:** run 37260166179 (commit 1f981b5): all 9 jobs green, at the first attempt; cross-job identity check green.

**Prices.**
- **Source:** `https://platform.claude.com/docs/en/about-claude/pricing`, read on 2026-10-04;
  shipped as version `2026-10-04.1`.
- **What it contains:** standard first-party prices for every Claude model on the page.
- **Checked:** `test_shipped_price_book_is_dated_and_sourced` checks six models against the page.
- **Please verify the file before accepting:** `src/tokli/pricing/price_book.yaml`.

## E2 — cache economics

**Dry run** (`test_e2_dry_run_self_test`, in the suite):
- **Setup:** an 8-turn synthetic conversation through two real Tokli instances, sent to a
  simulated prompt cache.
- **First attempt:** it **found a defect**. Relative error +0.98: the candidate arm's history
  changed between requests (TOKLI_EVIDENCE, "E2 dry run").
- **After S6 SCR-001:** +0.14, within ±0.25.
- **The residual is a unit effect of the simulator:** JSON escapes count as bytes there.

**Real run** (2026-10-05, by the human; `evals/experiments/e2_result.json`):
- **Setup:** `claude-sonnet-5`, 12 turns, 2 arms, 24 calls, price book `2026-10-04.1`.
- **Input-side cost:** baseline $0.2890, candidate $0.1607. The observed saving is
  **$0.1283 (44 % of the input-side cost)** on this synthetic conversation.
- **Tokli's positional prediction:** $0.1537 (range $0.0582–$0.7066). Relative error
  **+0.198**, within ±0.25: **pass**.
- **Both runs overestimate slightly** (+0.14 dry, +0.20 real). A small part of the saving in old
  history is placed in the region written to cache, at the write price, where the provider
  read it from cache.
  - Cause: the region boundary is an estimate, scaled by `k`.
  - Effect: the dashboard figure leans high by about a fifth on this traffic. The range always
    contains the observed value.

## S6 SCR-001 — the earlier segment's change wins

- **Approved 2026-10-05:** "ok, basta che vinca il compressore piu' efficace" (ok, as long as the
  more effective compressor wins).
- **Defect:** a later read identical to an earlier re-read made the re-read a reference target.
  CC-019 then rejected `reread_by_reference` on it, so history already sent changed.
- **Fix:**
  - the change of the earlier segment is kept, and the later stub is reverted
    (`reference_target_changed`);
  - the reverted segment is offered once more to every pruner. In the case found it becomes
    notes too, so both re-reads stay compressed and no history changes.
- **New tests:**
  - `test_reread_stays_when_a_later_read_duplicates_it` (regression; failed before the fix);
  - `prop_history_stays_stable_with_both_reference_compressors`.
- **Rewritten to the new rule:**
  - `test_reference_target_integrity_enforced`;
  - `test_reread_source_integrity_enforced`;
  - `test_terminal_stops_chain`: its fake now applies only to stubs, so it still tests CC-009.

## Architecture changes

**New modules:**
- `tokli.pricing` (`book`, `cost`, the shipped `price_book.yaml`);
- `tokli.app.regions`;
- `tokli.app.money`.

**Changed modules:**
- `SegmentPlace` lives in `tokli.domain.models`;
- `segment_places` is in the Anthropic protocol module.

**Contracts:**
- the `tokli.pricing` layer;
- telemetry and compression never import pricing;
- pricing never imports storage, compression, protocols or HTTP.

**Telemetry:**
- schema v4: `saved_cache_read`, `saved_cache_write`, `saved_input` in `requests` and
  `compressor_stats`;
- migrated forward in place (`test_schema_migration_v3_to_v4`).

**Engine (SCR-001):**
- reverting a stub and a second pass for reverted segments;
- the request-scope pass is split into `_pruner_pass`.

**Services** carry `prices`. The doctor shows a "Prices" section and the check "price book
valid". The goldens are updated.

## Measured performance

**Paired E9 run** against `main` (2196c88 + S8f) in a worktree, 20 iterations each,
`benchmarks.compare`:
- every bucket within 0.86×–1.19×, except `10k_estimate_cold` at 1.28× ("warn");
- that bucket is 0.41 ms against 0.32 ms, on the unchanged estimate path (E9 passes `saved=0`,
  so no places are computed): noise.

**Saving regions, off the latency path:**
- `segment_places` first scanned every segment for each part, which is quadratic: 11.6 ms at
  200k tokens.
- It now groups the segments once: 2.9 ms at 200k and 6.2 ms at 400k tokens (warm).

## Observability evidence

- **Reason codes:** `no_price_book`, `no_price_for_model`, `usage_unavailable` (money);
  `reference_target_changed` (TOKLI_OBSERVABILITY §4).
- **New fields:** in the schema (v4), the API contract (`definitions.schema.json`:
  `money_figure`, `request_cost`) and the retention job (rows are pruned whole).
- **Recent requests** show each request's money saved.
- **Canary scans** cover the new endpoints' payloads (`test_api_returns_no_content_or_credentials_s3`).

## Known limitations

**Prices not modelled:** fast mode, batch, data residency (1.1×) and cloud platforms. These are
standard first-party prices only.

**Where the split is null** (proportional fallback, labelled):
- `k` outside its range;
- partial usage;
- rows written before schema v4.

**Rewrites caused by Tokli are not deducted.** These are configuration changes and
`history_rewritten` requests. They are shown as caveats (TC-020).

**The region boundary is an estimate** scaled by `k`. A saving near the boundary can be priced
in the wrong region. E2 measures the effect.

## Unresolved questions

1. **The slight overestimate** (+14 % to +20 % on E2's conversation).
   - **Option:** a tighter boundary, by counting the forwarded request's structure the way the
     provider does.
   - **Recommendation:** watch it on dogfood first. Revisit only if real traffic shows a
     larger gap.
2. **The pipeline stage limit (PL-005)** is still open from S8f.

## Gate 2 record

- **Date:** 2026-10-05.
- **The human's words:** "accetto s6".
