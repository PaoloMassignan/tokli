# ADR 0007 — Telemetry schema v3: input tokens of accepted invocations

Status: accepted (S3, 2026-10-03) · Related: SPEC 013 TC-016, ADR 0003, ADR 0005

## Context

TC-016 (approved at S3 Gate 1) asks for the **average saving % per accepted invocation** of each
compressor. `CompressorStats.tokens_in` sums the input of every applicable invocation, accepted or
rejected, so the percentage cannot be computed from the stored rows. The engine knows each
invocation's input, so the number exists at run time but is not persisted.

## Decision

- **Schema version 3** adds `compressor_stats.tokens_in_accepted INTEGER`: Σ of the estimated
  input tokens over the accepted invocations of that compressor in that request.
- The engine counts it in `CompressorStats` alongside `tokens_in`.
- **Migration:** the forward migration of ADR 0005 adds the column. Rows written before v3 have
  `NULL`. The aggregate ignores them, and its reason says so when no row has the value.
- Average saving % per accepted invocation = Σ marginal saved / Σ `tokens_in_accepted`, over rows
  where it is known. Rejected invocations save nothing, so Σ marginal saved over a row equals the
  saving of its accepted invocations.

## Alternatives considered

- **Changing TC-016 to "saving % of processed tokens"** (`marginal saved / tokens_in`): no schema
  change, but it answers a different question and needs a spec change after approval. Rejected:
  the requirement is implementable.
- **Storing it in `skip_reasons` JSON:** mixes unrelated data. Rejected.

## Consequences

- An S2 build refuses a database migrated by S3 (newer version), as in ADR 0005.
- Tests: `test_stats_record_tokens_in_of_accepted_calls` (engine) and the forward migration tests
  (v1 → v3 and v2 → v3).
