# SPEC 008 — Token measurement

Status: **Approved for S0 (2026-09-29)**: TM-006, TM-007, TM-010, and the `tokens.default` / `tokens.model_map` schema. Other requirements: Draft. · Slice: S0 (tokenizer), S1 (estimates), S2 (exact + calibrated) · Related: TOKLI_TELEMETRY_AND_COST.md §1
Approved for S1 (2026-09-30): TM-001, TM-002, TM-005 (estimate label), TM-008.

## Purpose
Count tokens deterministically and label every figure with how it was obtained.

## Rationale
- Provider-reported usage is the reference. A local tokenizer gives an estimate, and for Claude models only a proxy estimate.
- Tokenizer data is provisioned explicitly. It is never downloaded at run time and never loaded at import time.
- Every figure carries its measurement basis (TOKLI_TELEMETRY_AND_COST §1).

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 008 rows).

## Requirements

| ID | EARS requirement |
|---|---|
| TM-001 | THE SYSTEM SHALL count tokens through a `TokenCounter` identified by a stable `tokenizer_id` (e.g. `tiktoken:o200k_base@<sha256-prefix>`). |
| TM-002 | THE SYSTEM SHALL select the tokenizer per request from `tokens.model_map` (ordered glob → tokenizer id), falling back to `tokens.default`. |
| TM-003 | WHEN provider usage is available for the forwarded request, THE SYSTEM SHALL record it as `exact` in the categories defined in TOKLI_TELEMETRY_AND_COST §4. |
| TM-004 | WHEN exact forwarded input usage and a local estimate of the whole forwarded request are both available, THE SYSTEM SHALL compute `k = exact_input_total / est_forwarded_request_total` and report the saving as `calibrated = est_saving × k`. |
| TM-005 | THE SYSTEM SHALL attach a `method ∈ {exact, calibrated, estimate}` to every token figure exposed by the API, UI, CLI and logs. |
| TM-006 | IF the configured tokenizer data cannot be loaded at startup (or, before a server exists, when `tokli doctor` checks it), THEN THE SYSTEM SHALL exit with an error naming the expected path and the provisioning command. |
| TM-007 | THE SYSTEM SHALL NOT load tokenizer data at module import time, and SHALL NOT download tokenizer data at runtime. |
| TM-008 | THE token counts for identical text and tokenizer SHALL be identical across supported operating systems and Python versions. |
| TM-010 | WHEN the user runs `tokli setup tokenizers`, THE SYSTEM SHALL obtain only the tokenizer files referenced by the effective configuration, from the official public source or from `--from-file PATH`, SHALL verify each file against a SHA-256 value pinned in Tokli's code, SHALL store it in `<data dir>/tokenizers/`, and SHALL refuse a file whose hash does not match. Tokenizer data SHALL NOT be bundled in the package. |
| TM-009 | WHEN `k` falls outside `[0.5, 2.0]`, THE SYSTEM SHALL record a `calibration_outlier` warning in the trace and SHALL report the saving as `estimate` for that request. |

## Acceptance criteria
- AC-TM-1: The same 200 fixture strings give identical counts on all CI OSes (fingerprint component).
- AC-TM-2: Starting with a missing tokenizer file prints `expected <path>; run 'tokli setup tokenizers'` and exits non-zero.
- AC-TM-3: Importing `tokli` with networking disabled and an empty cache does not fail.
- AC-TM-4: API responses for summary/compressors/requests include `method` on every token field (schema test).
- AC-TM-6 (TM-010): with a fake source serving a file with the pinned hash, setup stores it and doctor reports it present. A tampered file is refused and nothing is stored. `--from-file` with a valid file works with the network blocked.
- AC-TM-5: With a synthetic usage of 1,100 and an estimate of 1,000, `k = 1.1` and a 100-token estimated saving is reported as 110 calibrated. With `k = 3`, the saving stays an estimate and an outlier warning is recorded.

## Test scenarios
`test_tokenizer_selected_by_model_map` · `test_token_counts_stable_fixture` (fingerprint) ·
`test_missing_tokenizer_fails_with_actionable_message` · `test_import_has_no_side_effects` ·
`test_starts_offline_with_provisioned_tokenizer` · `test_every_api_token_field_has_method` ·
`test_calibration_factor` · `test_calibration_outlier_falls_back_to_estimate` ·
`test_setup_tokenizers_verifies_sha256` · `test_setup_tokenizers_from_file` · `test_token_counts_match_reference_values`

## Open questions
- ~~Q7~~ Resolved 2026-09-29: tokenizer data is not bundled. It is provisioned by `tokli setup tokenizers` (TM-010).
- E3 decides whether `o200k_base` or `cl100k_base` is the better proxy for Claude.
