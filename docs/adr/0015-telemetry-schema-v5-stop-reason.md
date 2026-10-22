# ADR 0015 — Telemetry schema v5: the response's stop reason

Status: accepted (S8j Gate 1, 2026-10-22) · Related: SPEC 003 AN-012, SPEC 013 TC-022, ADR 0005, ADR 0014

## Context

- **Two compressors may draw provider refusals.** S8c and E10(f) measured them on synthetic
  conversations for `edit_args_on_resume` and `outline_first_read`, both SELECTIVE and off by
  default. The human runs the first and wants the second available.
- **Tokli cannot see a refusal in real use.** The usage parser already reads the response
  passively (AN-005, AN-006), but it keeps only token counts. Without the stop reason, real
  traffic shows the saving and never the damage.

## Decision

- **Schema version 5** adds `requests.stop_reason TEXT`. The usage parser reads it from the same
  passive copy it reads usage from: the top-level field, or the last `message_delta`.
- **Allowed values:** values matching `^[a-z_]{1,32}$` are kept, any other string becomes `other`,
  and unknown is `NULL`. A closed vocabulary is not hard-coded, because providers add stop
  reasons; the pattern keeps free text out of the database.
- **Migration:** the forward migration of ADR 0005 adds the column. Rows written before v5 have
  `NULL`.
- **The request API view** shows the field. No aggregate is added in S8j: the refusal rate by
  `history_rewritten` or by compressor is a query over existing rows.

## Alternatives considered

- **A boolean `refused`:** it loses `max_tokens` and `pause_turn`, which also matter when judging
  a compressor. Rejected.
- **Logging only, no persistence:** logs rotate and cannot be joined with the per-compressor
  statistics. Rejected.

## Consequences

- **Tests:** stop reason parsing for streams and bodies (any chunk split, as the usage parser),
  migration from v4, the API field.
- **Privacy:** an enum-like token, never response text. The pattern enforces this.
- **Portability:** none.
