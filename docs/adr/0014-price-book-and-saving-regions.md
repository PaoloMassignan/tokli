# ADR 0014 — Price book and saving regions (schema v4)

Status: accepted (S6, 2026-10-04; approved at S6 Gate 1) · Related: SPEC 013 TC-004…TC-009,
TC-017…TC-020; SPEC 015 API-002, API-013; ADR 0003, 0005, 0007 (telemetry schema);
TOKLI_TELEMETRY_AND_COST §5

## Context

The human asked for a money saving close to the real one, after the provider cache.

In the developer's sessions (TOKLI_EVIDENCE, E5b-lite):
- 64 % of cost is cache reads, priced at 0.1× the input price (0.05× on Claude Opus 5.5);
- 27.5 % is cache writes, priced at 1.25× (5-minute) or 2× (1-hour).

**A token saved is worth very different amounts depending on where it sits:**
- in the cached prefix, it would have been a cache read;
- in the part written to cache, a cache write;
- in the uncached tail, an input token.

**The average-mix method ("proportional") blurs this.** It overvalues savings in history and
undervalues savings in the newest turn.

**The provider reports the region sizes per request.** Tokli knows the forwarded offset of every
segment it changed. Neither the regions nor the offsets survive the request today, and money
is computed later, at query time (ARCH §5: telemetry does not import pricing).

## Decision

**1. New module `tokli.pricing`.**
- **What it holds:** the price-book model, its loader and matcher, and the cost functions.
- **What it imports:** `tokli.domain` only.
- **Import contracts:**
  - telemetry and compression never import pricing (TC-009);
  - pricing never imports HTTP, telemetry or compression;
  - the app layer wires pricing into the metrics use cases.

**2. The price book.**
- **Shipped file:** `tokli/pricing/price_book.yaml` (dated, sourced).
- **User file:** an optional `<data>/price-book.yaml`, whose entries come first.
- **Loading:** both are read strictly at startup; an invalid file is a startup error.
- **Arithmetic:** prices are decimals per million tokens, and money is computed with `decimal`.

**3. Saving regions recorded at completion (schema v4).**
- **Columns:** `saved_cache_read`, `saved_cache_write`, `saved_input` (integers, estimate
  units, nullable), added to `requests` and to `compressor_stats`.
- **How they are computed:**
  - when the request completes, off the latency path, next to the calibration;
  - from each changed segment's forwarded offset in provider order (tool definitions, system,
    messages), as counted by the whole-request estimator;
  - against the usage regions divided by `k`.
- **Rounding:** largest remainder, so the parts sum exactly to the saving they split.
- **Migration:** the forward migration (ADR 0005) adds the columns. Older rows keep null and are
  priced with the proportional fallback, labelled.

**4. Money stays a query-time product.** A price-book change re-prices history by the
`effective_from` rule (TC-008). Nothing in money is persisted.

## Alternatives considered

| Alternative | Why not |
|---|---|
| **Proportional only** (the earlier Draft TC-004) | Simple, but it misprices the two places where Tokli saves: old history, worth very little, and the new tail, worth a lot. |
| **Persist money per request** | Freezes prices into the database. A corrected price book could not fix history. |
| **Persist per-segment offsets** | More rows and more data about request shape than needed. Three integers per row carry the whole answer. |
| **Compute regions at query time** | Offsets would have to be persisted anyway (previous row). |

## Consequences

**Tests:**
- region-split unit tests and a property test (the parts sum to the saving);
- hand-computed cost tests;
- the v3 → v4 migration test;
- import contracts for `tokli.pricing`;
- API contract schemas for money figures.

**Portability:** UTF-8 YAML; `decimal` arithmetic gives the same figures on every OS.

**Migration:**
- schema version 4;
- a v3 database migrates forward in place, and older Tokli versions refuse a v4 database
  (TC-012);
- no config key changes; the user file is optional.

**Limits:**
- Only standard first-party prices are modelled: no fast mode, batch, data residency or cloud
  platforms.
- The region boundaries are estimates scaled by `k`.
- The order of regions is the Anthropic one. Other protocols bring their own mapping when they
  arrive.
