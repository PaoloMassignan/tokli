# S8l SCR-003 — A money method for the keepalive's saving

Status: **approved** (2026-10-23, at Gate 2: "I choose b and approve the SCRs" (translated
from Italian)). Applied to the spec and traceability.

## 1. Affected requirements and acceptance criteria

- **SPEC 015 API-002** (approved for S6): every money figure is
  `{estimate, low, high, method, currency, price_book_version, basis}`, and a money `method` is
  `provider_usage` (the forwarded cost) or, for a saving, `positional`, `proportional` or
  `assumes_uncached`.
- **SPEC 013 TC-025** (approved for S8l): the `keepalive` block carries the ping cost, the
  estimated saving and the net, as estimates with a basis.
- No acceptance criterion changes; AC-TC-20 gains the method check.

## 2. Evidence

- The full suite (2026-10-23) failed `test_api_contract_schemas_s3`: the summary carried an
  unexpected `keepalive` member, and its first figures had no `method`.
- **The ping cost** is the provider usage of the pings at the price book: `provider_usage` fits
  exactly.
- **The saving** is neither a compression saving nor a forwarded cost. It is a counterfactual:
  each bridged request's cache read, priced at the write price of its lifetime minus the read
  price (TC-025). None of `positional`, `proportional` or `assumes_uncached` describes it.

## 3. Why the current requirement should change

TC-025 and API-002 cannot both hold for the saving and the net without a method value that
API-002 does not list.

## 4. Proposed change (exact new text)

- **API-002**, its second sentence becomes: "A money `method` is `provider_usage` (the forwarded
  cost: provider usage at the price book), or for a saving `positional`, `proportional` or
  `assumes_uncached` (TC-004, TC-006), or, for the cache keepalive's saving and net,
  `bridged_cache_reads` (TC-025: the bridged requests' cache reads at the write price of their
  lifetime minus the read price); a total carries the weakest of its parts in that order and,
  when they differ, `method_shares` (the share of the estimate per method). (S6, S8l SCR-003.)"
- **The net** carries `bridged_cache_reads`, the method of its estimated part.
- **The keepalive figures** may be negative (the net); `low` and `high` equal the estimate,
  because the saving's inputs are exact usage and prices.

## 5. Impact on tests

- `tests/contract/api/definitions.schema.json` gains `keepalive_money_figure`;
  `metrics_summary.schema.json` gains the required `keepalive` block.
- `test_keepalive_summary_hand_computed` checks the methods.
- `test_every_api_money_field_has_method` is unchanged; with the keepalive off, the block's
  figures are `{value: null, reason}`.

## 6. Impact on architecture

None.

## 7. Compatibility and migration

- The summary gains one member; API clients that ignore unknown members are unaffected. The
  dashboard reads it (UI-015).
