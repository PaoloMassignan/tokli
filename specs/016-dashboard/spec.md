# SPEC 016 — Web dashboard

Status: Draft · Slices: S3 (overview + compressors + recent), S4 (settings), S6 (cost), S9 (diagnostics)

## Purpose
Operational visibility first: how much is saved, by which compressor, at what latency. Then
simple control: policy and per-compressor enable/disable.

## Pages

| Page | Content |
|---|---|
| Overview | Cards: original tokens, forwarded tokens, saved tokens, saving %, estimated money saved (with range). Each card shows its method label. Time-range picker; filters: provider, model, compressor kind. Saved-tokens time series. |
| Compressors | One row per registry entry: name, kind badge (LOSSLESS / SELECTIVE / LOSSY / UNKNOWN), enabled toggle, availability, considered / applicable / accepted, tokens processed, marginal saved, share of total saving, avg saving % per accepted call, zero-benefit rate, failure rate, total and avg latency, tokens saved per ms, estimated money saved. Flag for "latency without benefit" (TOKLI_TELEMETRY_AND_COST §3). Note on order dependence of marginal attribution. |
| Recent requests | Table of recent requests (time, provider, model, outcome/reason, tokens with method, overhead). Detail view renders the trace (TOKLI_OBSERVABILITY §3). No content. |
| Settings | Global policy switch (LOSSLESS ONLY / LOSSY ALLOWED) with the explanation of UI-010. Compressor toggles (same as the Compressors page). Locked keys show their source. |
| Diagnostics | Doctor report, fingerprint, degraded checks, debug-content banner state. |

## Requirements

| ID | EARS requirement |
|---|---|
| UI-001 | THE dashboard SHALL obtain all data from `/tokli/api` and SHALL contain no compressor-specific logic beyond rendering fields it receives. |
| UI-002 | THE dashboard SHALL display the `method` label next to every token figure, and "estimate" plus the range next to every money figure. It SHALL display "—" with the reason when a value is unavailable. |
| UI-003 | THE dashboard SHALL show compressors with their kind **and equivalence** ("lossless · exact", "lossless · structural", "lossless · by reference", "selective", "lossy", "unknown"), their declared assumptions and the status of their evaluation record (none / provisional / smoke / full, with verdict), and SHALL visually distinguish LOSSY/SELECTIVE/UNKNOWN from LOSSLESS. |
| UI-004 | WHEN the policy is LOSSLESS ONLY, THE toggles of non-LOSSLESS compressors SHALL be shown as "not permitted by policy" rather than hidden. |
| UI-005 | WHEN a setting is locked by env/CLI, THE control SHALL be disabled and show the source. |
| UI-006 | THE dashboard SHALL be served as static files from the Tokli package, with no build step and no external network resources (no CDN). |
| UI-007 | WHILE debug-content mode is active, THE dashboard SHALL show a persistent, non-dismissible banner. |
| UI-008 | THE dashboard SHALL remain usable at 360 px width and SHALL respect `prefers-color-scheme`. |
| UI-009 | THE Overview page SHALL show the overhead distribution per size bucket (TC-013) with the product target drawn as a reference line labelled "target (not a limit)". THE Compressors page SHALL show each compressor's `cost_class`, average latency and `skipped_budget` rate, next to the effective `request_budget_ms`. |
| UI-010 | THE Settings page SHALL explain the policies in these words: LOSSLESS ONLY — "Tokli only applies transformations that provably keep all information in the request: exactly, structurally (e.g. JSON whitespace), or by reference to an identical earlier tool result. This does not guarantee identical model behaviour. Defaults are chosen from evaluations." LOSSY ALLOWED — "Also allows transformations that drop information: selective ones keep a declared part verbatim, lossy ones do not. Enable them only with evidence that your tasks are not affected." |

## Acceptance criteria
- AC-UI-1: the static bundle contains no string matching a compressor id (lint), except test fixtures.
- AC-UI-2: a browser test (Playwright, headless) renders Overview, Compressors and Recent with API fixtures, and every numeric token cell has an adjacent method label.
- AC-UI-3: toggling a compressor issues `PATCH /tokli/api/config` and re-renders from the response.
- AC-UI-4: offline rendering: with network blocked except loopback, all assets load.

## Test scenarios
`test_ui_has_no_compressor_specific_code` · `test_ui_renders_method_labels` · `test_ui_toggle_patches_config` ·
`test_ui_policy_marks_non_lossless_not_permitted` · `test_ui_locked_settings_show_source` · `test_wheel_contains_ui_assets` ·
`test_ui_assets_load_offline` · `test_debug_content_banner_visible` ·
`test_ui_shows_equivalence_assumptions_and_eval_status` · `test_ui_overhead_target_is_reference_line` · `test_ui_policy_explanations_text`
