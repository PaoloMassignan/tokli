# S6 — Spec review

## Slice scope

From TOKLI_ROADMAP.md, S6 "Pricing and cost estimates":
- a price book (dated, sourced), model matching, and query-time cost with method and bounds;
- dashboard cost cards and the estimated money saved per compressor;
- E2 (cache economics) executed; the cost method validated or revised.

## Specs and requirements in scope

| Spec | Requirements |
|---|---|
| SPEC 013 | TC-004…TC-009, AC-TC-3…AC-TC-5 |
| SPEC 015 | API-002 money figures; API-012 retired |
| SPEC 016 | Overview "estimated money saved" card; Compressors "estimated money saved" column; UI-002 for money |
| SPEC 012 | QE-009…QE-011 replace QE-018 (cost caps), if P7 says yes |
| Docs | TOKLI_TELEMETRY_AND_COST §5 |

## Out of scope

- OpenAI prices (S5/S7 bring those protocols).
- The cost of cache rewrites caused by Tokli itself (P8).
- Diagnostics (S9).

## The human's steer (2026-10-04)

"Vorrei che il risparmio fosse quello simile al reale. Dopo cache?": the saving shown should be
close to the real one, after the effect of the provider cache.

## 1. Ambiguities

| Req | Question | Proposed reading |
|---|---|---|
| TC-004 | "Method `proportional`" prices the saving at the forwarded request's average mix. Is that close enough to the real saving? | No, see P1. Tokli knows **where** each saving sits; the provider reports **which part** of the request was read from cache, written to cache, or sent uncached. |
| TC-004 | `[low, high]` bounds: what do they bound? | The uncertainty of the method: `low` = every saved token at the cheapest present price, `high` = at the most expensive one. Unchanged, so the range stays honest. |
| TC-008 | Which entry wins when several `match` globs fit a model? | Implementation decision (§8): the most specific pattern (fewest wildcards, then longest), then the latest `effective_from` not after the request. |
| UI | "Money saved" on a subscription (Claude Pro/Max via OAuth) is not money actually paid. | See P3. |

## 2. Contradictions

- **API-012 vs S6.** API-012 ("no_price_book" until S6) is superseded by TC-004/TC-005. It is
  retired with a note, not deleted.
- **QE-018 vs QE-009/010.** QE-018 applies "until a price book exists (S6)". From S6 the money
  caps apply, unless P7 defers them.

## 3. Missing behaviour

1. **Where a saving sits in the request.** Nothing records it today.
   - **What the positional method needs** (P1): for each request, the saved tokens split into the
     three regions of the provider's usage: cache read, cache write, uncached input.
   - **The order:** in Anthropic requests the cached prefix comes first, then the part written
     to cache, then the uncached tail.
   - **How Tokli places a saving:** from the forwarded position of each changed segment
     (whole-request estimate, off the latency path, TM-004), scaled by `k`, compared with the
     region sizes in `usage`.
2. **A user price book.** The spec says "overridable by the user", but not where or how. See P5.
3. **The no-usage case** (TC-006) and the no-position case (old rows written before S6) need a
   fallback. Proposed: the proportional method, labelled as such.

## 4. Portability concerns

- **Price-book loading.** YAML is read with an explicit UTF-8 encoding, and money is computed
  with `decimal`, not float, so every OS gives the same result. Dates are UTC.
- **The user override file** sits in the data directory (CP paths), never relative to the CWD.

## 5. Observability requirements (§8 checklist)

- **No new span on the request path:** cost is computed at query time.
- **The region split** is computed at record time, off the latency path, next to the existing
  calibration. It reuses the measurement span.
- **New reason codes:** `no_price_book`, `no_price_for_model`, `assumes_uncached`,
  `positions_unavailable` (the fallback).
- **New telemetry columns,** schema v4, migrated forward: the three region splits per request and
  per compressor stats row. They go into the API contract and the retention job.
- **Recent-request detail** shows the request's cost block.

## 6. Architectural risks

- **New module `tokli.pricing`** (allowed by ARCH §4). Its import contracts are added:
  - pricing imports only the domain;
  - telemetry never imports pricing (TC-009);
  - compression never imports pricing or telemetry.
- **Schema v4** is a persistence change. It needs an ADR before merge (CLAUDE.md §6).
- **The region split needs segment positions** from the protocol estimator. That is a small
  extension of the existing whole-request estimate (`tokli.protocols.anthropic_messages`). It
  adds no new dependency direction.
- **No seam beyond the price-book file.** One shipped file, one optional user file, one loader.

## 7. Product questions (for the human)

**P1. How to price the saving: positional or proportional?**
- **Proportional** (current Draft TC-004): saved tokens × the request's average price mix. A
  saving in the uncached tail is undervalued; one in the cached history is overvalued.
- **Positional** (proposed): each saved token is priced by the region it sits in.
  - In the cached prefix → cache-read price.
  - In the part written to cache → cache-write price (5 m or 1 h).
  - In the uncached tail → input price.
- **What positional gives, summed over requests,** is what the developer's sessions showed
  (E5b-lite): a token saved in history costs a cache write once when it first appears (and again
  after each rewrite after a pause), then a cache read in every later request.
- **What it costs to build:**
  - three integer columns per request and per compressor row;
  - offsets from the existing whole-request estimate.
- **Recommended: positional.** Proportional stays as the fallback, with its own label.

**P2. Money per compressor.** Recommended: the same positional split, stored per compressor
stats row, so the Compressors page shows each compressor's money saving on the same basis.

**P3. Subscriptions.** With Claude Pro/Max (OAuth) the developer does not pay per token. The
figure still shows the value at API prices.
- Recommended: label it "value at API prices" when the request's credential is OAuth, and
  "estimated money saved" when it is an API key.
- Totals that mix both are labelled "value at API prices".

**P4. Which prices are shipped, and who checks them.**
- **Recommended models:** only Anthropic models, since only the Anthropic protocol exists:
  - the current families (`claude-opus-5*`, `claude-sonnet-5*`, `claude-haiku-4-5*`);
  - the 4.x families still accepted by the API.
- **Source:** during GREEN, Claude reads the official pricing page (no cost, no credentials) and
  records the date and the URL in the file.
- **Check:** **the human verifies the values** before Gate 2.

**P5. User override.** Recommended: an optional `<data>/price-book.yaml`, same format. Its
entries are taken before the shipped ones. No UI editing in S6. Doctor shows the price-book
version and whether an override is active.

**P6. E2: validating the method (costs money, run by the human).**
- **The run:** a short scripted API conversation with cache markers (synthetic content, about 12
  turns), run twice with default compressors off and on.
- **The check:** the cost difference that Tokli *predicts* (positional) is compared with the
  difference *observed* from provider usage at the price-book prices.
- **Pass criterion:** within ±25 %.
- **Budget:** estimated at a few dollars on `claude-sonnet-5`; the exact plan is shown before
  any call.
- Recommended: yes, as the slice's exit evidence, in place of the roadmap's 20-turn Claude Code
  session. A real Claude Code session cannot be reproduced exactly.

**P7. Cost caps for `tokli eval`.** With a price book, QE-009/010 (confirmation with an
estimated cost, stop at estimate × 1.2 or `--max-cost`) replace QE-018. `--max-calls` stays for
models without a price. Recommended: yes, in S6; it is small and already specified.

**P8. Cache rewrites caused by Tokli.** Enabling or disabling a compressor, or a
non-prefix-stable compressor (`history_rewritten`), makes the provider rewrite its cache once.
- **Not deducted from the saving in S6:** the counterfactual is not observable per request.
- Recommended: the summary shows the count of requests with `history_rewritten` and of
  `config_hash` changes in the range, as a caveat next to the money figure.

**P9. Currency.** Recommended: USD only, as the providers publish.

## 8. Implementation decisions (Claude)

- **Price-book format:** TOKLI_TELEMETRY_AND_COST §5, validated with strict pydantic; prices per
  million tokens as decimals.
- **Matching:** the most specific glob wins (fewest `*`, then the longest literal), then the
  latest `effective_from` ≤ the request's `ts_start`.
- **Money computation:** query time, `decimal`, rounded only for display (6 decimals in the
  API).
- **Region split at record time:**
  - computed in estimate units, from the cumulative forwarded offsets of changed segments,
    against region sizes = usage categories / `k`; without an in-range `k` the split is null
    (TC-017) and the proportional fallback applies;
  - a segment straddling a boundary is split linearly.
- **Fallback:** without usage, TC-006; without positions (rows before v4), proportional.
- **Timeseries:** carries token figures only. Money is in the summary, the compressors endpoint
  and the requests endpoints (API-013).
- **Prices:** from the official Anthropic pricing page, read on 2026-10-04
  (`platform.claude.com/docs/en/about-claude/pricing`). Fast mode, batch, data-residency (1.1×)
  and cloud-platform prices are not modelled: standard first-party prices only (known
  limitation).
- **API shape:** API-002 money figure `{estimate, low, high, method, currency,
  price_book_version}`, with `method` ∈ {`positional`, `proportional`, `assumes_uncached`} and,
  for mixed totals, the share of each method.

## 9. Test plan (after Gate 1)

| Req / AC | Tests |
|---|---|
| TC-004, AC-TC-3 | `test_cost_positional_estimate_and_bounds`: hand-computed, savings placed in each region |
| TC-004 fallback | `test_cost_proportional_without_positions` |
| TC-005, AC-TC-4 | `test_cost_unavailable_without_price` |
| TC-006 | `test_cost_assumes_uncached_without_usage` |
| TC-007 | `test_no_output_savings_claimed` |
| TC-008, AC-TC-5 | `test_price_effective_dates`, `test_price_match_most_specific` |
| TC-009 | import contracts for `tokli.pricing` |
| Region split | `test_saving_regions_hand_computed`, `prop_saving_regions_sum_to_saving` |
| Schema v4 | `test_schema_migration_v3_to_v4` |
| API | contract schemas updated, `test_every_api_money_field_has_method` |
| P3 | `test_oauth_cost_labelled_value_at_api_prices` |
| P5 | `test_user_price_book_overrides_shipped` |
| UI (Playwright) | `test_ui_cost_card_shows_estimate_range_and_method`, `test_ui_compressor_money_column` |
| P7 | `test_eval_requires_confirmation_or_max_cost`, `test_eval_stops_at_cost_cap`, `test_eval_requires_max_calls_without_pricing` |
| P6 | E2 script with a dry-run self-test (fake upstream), then the human's run |

## Gate 1 record

- **Date:** 2026-10-04.
- **The human's words:** "ok per tutto. approvo s6". P1–P9 were answered with the recommendations.
- **Spec delta:**
  - SPEC 013: TC-004 and TC-008 rewritten; TC-017…TC-020 and AC-TC-13…16 added; AC-TC-3
    rewritten;
  - SPEC 015: API-002 money fields, API-012 retired, API-013 added;
  - SPEC 016: UI-013;
  - SPEC 012: QE-018 retired and restated with the price book;
  - all of it in the S6 commit (`git diff main -- specs/`).

## Notes after Gate 1 (implementation, recorded)

- **Forwarded cost method.** The forwarded cost has its own method, `provider_usage` (exact
  usage × the price book). API-002 was worded to include it, and the contract schema enumerates
  it.
- **E2 dry run.** The dry run found the defect fixed by S6 SCR-001 (approved 2026-10-05).
