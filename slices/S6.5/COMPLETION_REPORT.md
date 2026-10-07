# S6.5 — Completion report

## Requirements implemented

Presentation, wording and layout were reviewed and changed under the S6.5-approved reading of
SPEC 016 UI-001…UI-013 and AC-UI-1…AC-UI-5. No API, schema or backend behaviour changed.

- UI-001 / UI-006: the bundle remains dependency-free, packaged static HTML/CSS/JS, reads only
  `/tokli/api`, and contains no compressor identity.
- UI-002: every rendered token value retains its method or unavailable reason. The saved-token
  time-series now has a reachable value/method table, and its visible maximum names its method.
- UI-003 / UI-004 / UI-005 / UI-010 / UI-012: kind, equivalence, assumptions, evaluation, lossless
  shortcut, lock source and verbatim opt-in remain reachable. The exact UI-010 and UI-012 wording is
  unchanged.
- UI-008: one responsive DOM works at 360 px, both colour schemes use a neutral palette plus one
  accent, and controls have an explicit focus indicator.
- UI-009: the compressor comparison puts effective budget, cost class, average latency and
  skipped-budget rate together in each detail. Every overhead group exposes n, p50, p95, p99 and
  max; the chart still labels the line “target (not a limit)” and never assigns pass/fail.
- UI-013: Overview and per-compressor money show estimate, range, plain-language method, basis and
  price-book version. Non-zero Overview caveats remain visible on separate lines.
- The approved Recent requests page definition now includes Provider. A native View button replaces
  the scripted clickable table row.

Deferred: UI-007 remains deferred until debug-content mode exists, as explicitly scoped by the
S6.5 brief. Diagnostics remains S9. No other requirement is deferred.

## Before and after

### Shared shell

- **Before:** metric filters appeared on every page; selected tabs, warnings and four compressor
  kinds used several unrelated colours; focus relied on browser defaults.
- **After:** filters appear only on Overview and Compressors and retain their values; the palette is
  neutral with one rust accent; every interactive element has a 3 px `:focus-visible` outline. One
  contextual Help button reveals field explanations only when requested.

### Overview

- **Before:** six equal cards led with request/original/forwarded counts; the method legend occupied
  the first screen; time-series methods and non-dominant overhead groups were not reachable.
- **After:** saved tokens, money and saving percentage come first. Request/original/forwarded totals
  are in “How this total is made”. The money card keeps only the estimate and range; its method,
  basis and price-book version move to contextual Help. The token-method legend and overhead
  explanation are also in Help. The time series has “Values and methods”, and overhead has a
  complete “All policies and configurations” table.

### Compressors

- **Before:** one 20-column table mixed the primary comparison with every diagnostic, with help only
  in hover `title` attributes. Per-compressor money omitted basis and price-book version.
- **After:** six columns answer Compressor, On, Kind, Tokens saved, Money saved and Attention. Each
  registry row is a native disclosure containing all former fields, visible definitions,
  assumptions and the grouped budget/latency information. Headers and disclosure summaries share
  one CSS grid, including right-aligned numeric columns. The summary money cell keeps estimate and
  range; method, basis and price-book version are in the compressor detail. Field explanations and
  marginal-attribution guidance are in Help.

### Recent requests

- **Before:** Provider was absent and a focusable table row simulated a control, accepting Enter but
  not Space.
- **After:** Provider is a column; every row has a native View button; the selected request is marked
  and its detail begins with provider, model and outcome before the unchanged trace. Money cells
  keep only estimate and range; the field descriptions are in contextual Help.

### Settings

- **Before:** approved kind explanations and all evaluation/assumption text were always expanded in
  a two-dimensional card grid, ahead of or competing with the controls.
- **After:** Lossless only is first and settings form one vertical list with stable “Enabled” labels.
  Exact kind explanations and configuration timing are in Help. Evaluation and assumptions are in
  an “Evidence and assumptions” disclosure.
  The UI-012 risk warning stays expanded beside its toggle.

## Tests and evidence

### Test-first evidence

The S6.5 tests were added before production changes. RED result:

```text
9 failed, 15 passed, 1 skipped
```

The nine failures were the approved missing behaviours: contextual filters, Overview hierarchy,
time-series methods, complete overhead detail, compact compressor detail, Provider/native request
action, explicit focus in both themes, and Settings disclosures. There were no import or fixture
failures.

### Final commands

```text
pytest -q
765 passed, 10 skipped in 423.91s

RUN_BROWSER_TESTS=1 pytest tests/ui -q
27 passed, 1 skipped in 58.90s

UI_SCREENSHOTS_DIR=<explicit path> RUN_BROWSER_TESTS=1 \
  pytest tests/ui/test_dashboard.py::test_ui_screenshots -q
1 passed in 13.61s

ruff check .
All checks passed!

ruff format --check .
150 files already formatted

mypy
Success: no issues found in 80 source files

lint-imports
Contracts: 7 kept, 0 broken
```

The full suite needs a process-local Git `safe.directory` in this sandbox because the checkout is
owned by the developer account while tests run as the sandbox account. Without it, the product
tests produced 764 passes and only `test_repository_contains_no_developer_paths` failed before its
assertion because `git ls-files` exited 128. With the process-local forward-slash path, that test and
the full suite passed. No user-level Git configuration was changed.

The ten full-suite skips are the documented browser, packaging and provisioned-tokenizer checks.
The browser suite was run separately. Its one skip is the conditional screenshot test, which was
also run separately with its output variable set and passed.

### Screenshot command

PowerShell:

```powershell
$env:RUN_BROWSER_TESTS = "1"
$env:UI_SCREENSHOTS_DIR = "<output-directory>"
python -m pytest tests/ui/test_dashboard.py::test_ui_screenshots -q
```

It writes 16 uncommitted PNGs: Overview, Compressors, Recent requests and Settings at 1280×900 and
360×740, each in light and dark colour schemes. The review artifacts for this run are under
`slices/S6.5/screenshots/` and are intentionally untracked.

### Existing tests changed

- `test_ui_compressor_money_column`: follows the compact summary and now also asserts basis and
  price-book version.
- `test_ui_shows_kind_equivalence_and_assumptions`: opens the native compressor detail before
  checking assumptions.
- `test_ui_request_detail_renders_trace`: activates the native View button.
- `test_ui_shows_equivalence_assumptions_and_eval_status`: opens “Evidence and assumptions”.
- `test_ui_policy_explanations_text`: opens Help; both exact strings remain the assertions.

No requirement assertion was weakened, skipped or deleted.

### Tests added

- `test_ui_filters_are_only_on_metrics_pages`
- `test_ui_overview_prioritises_savings_and_keeps_totals_reachable`
- `test_ui_timeseries_values_show_methods`
- `test_ui_all_overhead_groups_and_percentiles_are_reachable`
- `test_ui_compressor_summary_and_full_details`
- `test_ui_recent_requests_show_provider_and_native_detail_button`
- `test_ui_focus_is_visible_in_both_colour_schemes` (light and dark cases)
- `test_ui_settings_primary_controls_and_disclosures`
- `test_ui_screenshots` (four pages × two viewports × two colour schemes)
- `test_ui_help_reveals_contextual_field_descriptions`
- `test_ui_recent_request_money_is_compact_with_descriptions_in_help`
- `test_ui_compressor_columns_share_one_alignment_grid`

`TOKLI_TRACEABILITY.md` maps the new requirement tests. Existing integration, contract, offline,
content-type and package assertions are unchanged.

## Architecture changes

None. The implementation remains the three existing static files under `tokli/ui/`; it introduces
no framework, dependency, build step, route, module, persistence change, abstraction or ADR. The UI
still communicates only with `/tokli/api`. Import contracts are green.

## Measured performance

Not applicable: S6.5 changes static presentation and adds no request, pipeline or backend path. No
latency measurement was claimed. The existing product target is still displayed only as a reference.

## Observability evidence

No new code path, span, decision, reason code, telemetry field, log or stored content was added. The
existing trace remains reachable from Recent requests and is preceded by clearer metadata. Existing
credential/content/privacy tests passed in the full suite.

## Known limitations

- The exact-size screenshots intentionally capture the requested viewport, not a full-page stitch;
  content below the fold is reviewed through the other viewport and the live-dashboard Gate 2 pass.
- Wide data tables scroll inside their container at 360 px. The page itself does not scroll
  horizontally.
- Screenshot PNGs are local review artifacts and are not committed.

## Unresolved questions

None for implementation. Human visual verification remains required by
`slices/S6.5/HUMAN_REVIEW.md`.

## Gate 2 feedback iterations

- 2026-10-06: the human requested that field descriptions stop cluttering the layout and appear
  only through a dedicated Help button. A regression test first failed because Help did not exist.
  The implementation now has one contextual Help button, lighter compressor money summaries and no
  permanently visible explanatory paragraphs except the risk-critical, approved UI-012 warning.
  Updated verification: browser `25 passed, 1 skipped`; screenshot `1 passed`; full suite
  `765 passed, 10 skipped`; Ruff, formatting, mypy and import contracts green.
- 2026-10-07: the human requested the same compact money treatment on Overview and Recent requests,
  plus better Compressor-table alignment. Overview now exposes full money provenance in Help;
  request rows retain only the required estimate and range, with definitions in Help; Compressor
  headers and summaries use the same alignment grid. Regression tests first failed in all three
  requested areas and then passed. Updated verification: browser `27 passed, 1 skipped`; screenshot
  `1 passed`; full suite `765 passed, 10 skipped`; Ruff, formatting, mypy and import contracts green.

## Gate 2 record

2026-10-07 · accepted with the human's words: “ok a tokli proseguiamo”.
