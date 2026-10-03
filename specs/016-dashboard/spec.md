# SPEC 016 — Web dashboard

Status: Draft · Slices: S3 (overview + compressors + recent), S4 (settings), S6 (cost), S9 (diagnostics)
Changed by S4 SCR-001 (2026-10-03): UI-004, UI-010, the Settings and Overview rows.
Approved for S3 (2026-10-03): Overview, Compressors (read-only), Recent requests; UI-001, UI-002, UI-003 (without evaluation status), UI-006, UI-008, UI-009, UI-011.
Approved for S4 (2026-10-03): Settings page; UI-003 (evaluation status), UI-004, UI-005, UI-010, AC-UI-3; saved tokens per compressor on the Overview.

## Purpose
Operational visibility first: how much is saved, by which compressor, at what latency. Then
simple control: policy and per-compressor enable/disable.

## Pages

| Page | Content |
|---|---|
| Overview | Cards: original tokens, forwarded tokens, saved tokens, saving %, estimated money saved (with range). Each card shows its method label. Time-range picker; filters: provider, model, compressor kind. Saved-tokens time series. Saved tokens per compressor (S4). |
| Compressors | One row per registry entry: name, kind badge (LOSSLESS / SELECTIVE / LOSSY / UNKNOWN), enabled toggle, availability, considered / applicable / accepted, tokens processed, marginal saved, share of total saving, avg saving % per accepted call, zero-benefit rate, failure rate, total and avg latency, tokens saved per ms, estimated money saved. Flag for "latency without benefit" (TOKLI_TELEMETRY_AND_COST §3). Note on order dependence of marginal attribution. |
| Recent requests | Table of recent requests (time, provider, model, outcome/reason, tokens with method, overhead). Detail view renders the trace (TOKLI_OBSERVABILITY §3). No content. |
| Settings | One toggle per compressor (enabling a compressor is the only control), with its kind, equivalence, assumptions and evaluation status. The "Lossless only" shortcut with the explanation of UI-010. Locked keys show their source. |
| Diagnostics | Doctor report, fingerprint, degraded checks, debug-content banner state. |

## Requirements

| ID | EARS requirement |
|---|---|
| UI-001 | THE dashboard SHALL obtain all data from `/tokli/api` and SHALL contain no compressor-specific logic beyond rendering fields it receives. |
| UI-002 | THE dashboard SHALL display the `method` label next to every token figure, and "estimate" plus the range next to every money figure. It SHALL display "—" with the reason when a value is unavailable. |
| UI-003 | THE dashboard SHALL show compressors with their kind **and equivalence** ("lossless · exact", "lossless · structural", "lossless · by reference", "selective", "lossy", "unknown"), their declared assumptions and the status of their evaluation record (none / provisional / smoke / full, with verdict), and SHALL visually distinguish LOSSY/SELECTIVE/UNKNOWN from LOSSLESS. |
| UI-004 | THE Settings page SHALL show one on/off toggle per compressor, and a shortcut "Lossless only" that switches off, in one change, every enabled compressor whose kind is not LOSSLESS. Next to every non-LOSSLESS compressor it SHALL say that it drops information. (S4 SCR-001.) |
| UI-005 | WHEN a setting is locked by env/CLI, THE control SHALL be disabled and show the source. |
| UI-006 | THE dashboard SHALL be served as static files from the Tokli package, with no build step and no external network resources (no CDN). |
| UI-007 | WHILE debug-content mode is active, THE dashboard SHALL show a persistent, non-dismissible banner. |
| UI-008 | THE dashboard SHALL remain usable at 360 px width and SHALL respect `prefers-color-scheme`. |
| UI-009 | THE Overview page SHALL show the overhead distribution per size bucket (TC-013) with the product target drawn as a reference line labelled "target (not a limit)". THE Compressors page SHALL show each compressor's `cost_class`, average latency and `skipped_budget` rate, next to the effective `request_budget_ms`. |
| UI-011 | THE dashboard SHALL be served at `/tokli/` with its assets under `/tokli/ui/`, with explicit content types (never derived from the host's file-type registry), and `tokli serve` SHALL print the dashboard address at startup. |
| UI-010 | THE Settings page SHALL explain the kinds in these words: Lossless — "Keeps all information in the request: exactly, structurally (e.g. JSON whitespace), or by reference to an identical earlier tool result. This does not guarantee identical model behaviour. Defaults are chosen from evaluations." Selective / lossy — "Drops information: selective ones keep a declared part verbatim, lossy ones do not. Enable them only with evidence that your tasks are not affected." (S4 SCR-001.) |

## Acceptance criteria
- AC-UI-1: the static bundle contains no string matching a compressor id (lint), except test fixtures.
- AC-UI-2: a browser test (Playwright, headless) renders Overview, Compressors and Recent with API fixtures, and every numeric token cell has an adjacent method label.
- AC-UI-3: toggling a compressor issues `PATCH /tokli/api/config` and re-renders from the response.
- AC-UI-4: offline rendering: with network blocked except loopback, all assets load.
- AC-UI-5 (UI-011): every asset is served with the content type of its extension (`text/html`, `text/css`, `text/javascript`, `image/svg+xml`) on all CI OSes.

Browser tests (AC-UI-2, UI-003, UI-008, UI-009) run with Playwright and headless Chromium in one CI job (Ubuntu, Python 3.12) and locally when Playwright is installed (ADR 0006). The evaluation-record status of UI-003 is shown from S4.

## Test scenarios
`test_ui_has_no_compressor_specific_code` · `test_ui_renders_method_labels` · `test_ui_toggle_patches_config` ·
`test_ui_policy_marks_non_lossless_not_permitted` · `test_ui_locked_settings_show_source` · `test_wheel_contains_ui_assets` ·
`test_ui_assets_load_offline` · `test_debug_content_banner_visible` ·
`test_ui_shows_equivalence_assumptions_and_eval_status` · `test_ui_overhead_target_is_reference_line` · `test_ui_policy_explanations_text` ·
`test_ui_shows_kind_equivalence_and_assumptions` · `test_ui_usable_at_360px` · `test_ui_assets_served_with_explicit_content_types`
