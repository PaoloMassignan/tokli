# S6.5 — Spec review

## Scope

Slice scope: presentation, wording and layout of the existing dashboard pages only. The JSON API,
its schemas, backend behaviour, compression, telemetry, pricing and configuration behaviour do not
change.

Requirements in scope: SPEC 016 UI-001…UI-013 and AC-UI-1…AC-UI-5, with particular attention to
UI-002, UI-003, UI-004, UI-005, UI-006, UI-008, UI-009, UI-010, UI-012 and UI-013. Supporting
requirements are SPEC 013 TC-013, TC-016, TC-019 and TC-020, and SPEC 015 API-001…API-004,
API-010, API-011 and API-013.

Explicitly out of scope: Diagnostics (S9), debug-content UI until that mode exists (UI-007), new
figures, endpoints or pages, API/schema changes, branding and changes to the approved UI-010 or
UI-012 wording.

Documents and implementation reviewed: `CLAUDE.md`, `AGENTS.md`, the S6.5 brief and human-review
checklist, SPEC 013/015/016, the S6.5 roadmap entry, ADR 0006/0009/0014,
`TOKLI_ARCHITECTURE.md` §5/§7/§8, `TOKLI_TEST_STRATEGY.md` §2/§8,
`TOKLI_OBSERVABILITY.md` §3/§8, `TOKLI_COMPRESSORS.md` §11,
`TOKLI_TELEMETRY_AND_COST.md`, the three files in `src/tokli/ui/`, and the relevant browser,
integration and packaging tests.

## 1. Findings

### Shared shell

| ID | Element | Finding and user impact |
|---|---|---|
| F1 | `src/tokli/ui/index.html` `header > #filters` | Range, provider, model and kind filters appear on all four pages, although Recent requests and Settings do not consume them. They look active where they have no effect and occupy most of the header at 360 px. |
| F2 | `src/tokli/ui/style.css` `:root`, `.badge.*`, `.flag` | The page uses blue, green, yellow, red and orange semantic colours. That conflicts with the brief's neutral palette plus one accent and makes the kind pills look like a generic status-badge system. Kind words already carry the meaning, so the extra palette is unnecessary. |
| F3 | `src/tokli/ui/style.css` `.card`, `.compressor-card`, `.badge` | Six filled KPI tiles, a grid of filled compressor cards and rounded badges make the page read as a collection of UI components rather than one careful tool. The repeated rounded surfaces add visual weight without adding information. |
| F4 | `src/tokli/ui/style.css` interactive selectors | There is no explicit `:focus-visible` treatment. Browser defaults may appear, but the dashboard does not guarantee the visible focus required by the brief or test it in either theme. |
| F5 | `src/tokli/ui/app.js` `show()` and `#status` | A load failure is reported in the shared header while the previous or empty panel remains. The message is reachable, but its relationship to the affected page is weak. This is not a behaviour change request; the status should remain shared and visually adjacent to the current page heading. |

### Overview

| ID | Element | Finding and user impact |
|---|---|---|
| F6 | `src/tokli/ui/app.js` `loadOverview()` / `#cards` | Requests, original tokens and forwarded tokens come before saved tokens and money. A user cannot answer the two primary questions—tokens saved and money saved—without scanning six equal-weight tiles. |
| F7 | `src/tokli/ui/index.html` `.legend` | The method legend is useful but permanently occupies the first screen. It explains secondary metadata before the user reaches the main numbers. |
| F8 | `src/tokli/ui/app.js` `savedChart()` / `#saved-chart` | The time-series bars encode saved-token figures, but the chart does not expose each bucket's value and method in visible text. The only number shown is the maximum, without its method. This makes the chart hard to inspect and leaves UI-002 incompletely represented. |
| F9 | `src/tokli/ui/app.js` `overheadChart()` / `#overhead-chart` | Only the most-used policy/configuration group is drawn. The note counts the other groups, but their distributions are not reachable. Within the chosen group only p50 and p95 are shown; n, p99 and max supplied for TC-013 are hidden. |
| F10 | `src/tokli/ui/index.html` overhead note and `overheadChart()` target label | The same reference is called both “goal” and “target”. Inconsistent naming makes the already careful “target (not a limit)” rule less clear. |
| F11 | `src/tokli/ui/app.js` `costCard()` | The cost caveats and price-book version are compressed into one dot-separated sentence beneath an already dense inline money figure. The required information is present, but it is hard to associate a caveat with the estimate. |

### Compressors

| ID | Element | Finding and user impact |
|---|---|---|
| F12 | `src/tokli/ui/app.js` `loadCompressors()` / `#compressors-table` | The only view is a 20-column table. The first questions—what is on, what saved, and what needs attention—are mixed with invocation counters and diagnostic rates. At 360 px the user must scroll far sideways before comparing compressors. |
| F13 | `src/tokli/ui/app.js` `columns` and `th[title]` | Column explanations exist only in `title` attributes and the page says “Hover”. They are unavailable to keyboard-only and touch users and are not reliably announced by assistive technology. |
| F14 | `src/tokli/ui/app.js` compressor `money()` cell | Each money cell shows estimate, range and method, but not its basis label or price-book version. UI-013 requires the same labels for each compressor as for the Overview figure. |
| F15 | `src/tokli/ui/app.js` `#budget` and metric columns | Effective request budget, cost class, average latency and skipped-budget rate all exist, but the budget is in a paragraph while the other three are separated across the wide row. UI-009 asks users to see them together. |
| F16 | `src/tokli/ui/app.js` compressor-name cell | Version and every assumption are expanded in the first column for every row. This makes rows tall and delays comparison of the measurements; the assumptions remain important but are secondary detail. |

### Recent requests

| ID | Element | Finding and user impact |
|---|---|---|
| F17 | `src/tokli/ui/app.js` `loadRequests()` / `#requests-table` | The table omits provider even though SPEC 016 lists time, provider and model. A user with more than one provider cannot identify the route from the list. |
| F18 | `src/tokli/ui/app.js` request `<tr tabindex="0">` | A table row is made clickable with JavaScript and responds to Enter only. It is not a native control, has no action name, and Space does not activate it. This conflicts with the brief's real-controls and keyboard requirements. |
| F19 | `src/tokli/ui/app.js` `showDetail()` / `#request-detail` | Detail appears after the whole table and programmatically scrolls into view, but the selected row is not identified and there is no explicit “View details” control. It is easy to lose context in a long list. |
| F20 | `src/tokli/ui/app.js` `showDetail()` | The trace is rendered as a raw preformatted block. That preserves the normative trace and is appropriate for technical detail, but the request summary has no provider/model/outcome heading to anchor it. |

### Settings

| ID | Element | Finding and user impact |
|---|---|---|
| F21 | `src/tokli/ui/index.html` `.kinds` | The two approved explanations are always expanded above the primary shortcut and toggles. They are essential reference text, but they push the controls below the first screen. |
| F22 | `src/tokli/ui/style.css` `.compressor-cards` and `.compressor-card` | A responsive grid of cards makes it harder to scan one on/off column and produces a long two-dimensional reading order. Settings are more naturally a single vertical list. |
| F23 | `src/tokli/ui/app.js` `renderSettings()` | Evaluation and all assumptions are expanded inside every card. They satisfy UI-003, but they compete with the on/off control and the UI-012 warning. |
| F24 | `src/tokli/ui/app.js` toggle labels | The visible “on”/“off” text is generated from the state at render time and the checkbox itself has a separate `aria-label`. The control is functional, but a stable visible label (“Enabled”) is clearer and avoids treating state text as the control name. |
| F25 | `src/tokli/ui/index.html` `#lossless-only` | The shortcut is visually no more prominent than Save retention, despite being the safe bulk action named by UI-004. The explanatory text is clear and must remain. |

## 2. Proposals

### P1 — Use a plain shell and contextual metrics filters

Keep the page switcher in the header. Show the existing filter form only on Overview and
Compressors, with a visible “Filters” label and the same values retained when switching between
those pages. Put the current page's load status immediately below it. Use neutral surfaces and one
accent for selected controls, focus and warnings. Replace filled tiles, rounded status pills and
decorative colour coding with spacing, rules, type weight and explicit words. Add a strong
`:focus-visible` outline in light and dark themes. No animations or transitions.

Requirements touched: UI-003, UI-008 (**within spec**); UI-001, UI-006 (**preserved within spec**).
No Spec Change Request is needed.

### P2 — Put saved tokens and money first on Overview; make complete data reachable

Render “Saved tokens”, the money basis label and estimate, and “Saving” first. Put requests,
original tokens and forwarded tokens in a native `<details>` labelled “How this total is made”,
along with the exact/calibrated/estimate legend. Keep saved tokens per compressor next. Keep the
time-series chart, and add a compact table in `<details>` with every bucket's numeric saved-token
figure and method. Use “target” consistently. Keep the overhead chart, then add a complete table in
`<details>` containing every policy/configuration group, size bucket, n, p50, p95, p99 and max. Put
price-book version and non-zero caveats on separate lines beneath the money estimate.

Requirements touched: UI-002, UI-008, UI-009, UI-013, TC-013 and TC-020 (**within spec**). No
Spec Change Request is needed.

#### Overview sketch — 1280 px

```text
Tokli        Overview  Compressors  Recent requests  Settings
             Filters: [Last 7 days] [Provider] [Model] [Kind]

Saved tokens                 Estimated money saved              Saving
12,340  calibrated           $0.84 estimate                     18.2 % estimate
                             $0.20–$1.48
                             by where the saving sits in cache
                             price book 2026-10-04.1

> How this total is made

Saved tokens per compressor
Compressor                 Kind                   Tokens saved       Share
JSON minify               lossless · structural          8,100       65.6 %

Saved tokens over time
[plain bar chart across available width]
> Values and methods

Time Tokli adds to each request
[p50/p95 chart; line labelled “target (not a limit)”]
> All policies and configurations
```

#### Overview sketch — 360 px

```text
Tokli
[Overview] [Compressors]
[Recent requests] [Settings]

Filters
[Last 7 days       ]
[Provider          ]
[Model             ]
[Kind              ]

Saved tokens
12,340  calibrated

Estimated money saved
$0.84 estimate
$0.20–$1.48
by where the saving sits in cache

Saving
18.2 % estimate

> How this total is made

Saved tokens per compressor
[internally scrolling table]

Saved tokens over time
[chart fitted to content width]
> Values and methods

Time Tokli adds to each request
[chart fitted to content width]
> All policies and configurations
```

### P3 — Give Compressors a compact comparison row and native detail per compressor

Keep one table row per registry entry, but limit the always-visible columns to Compressor, On,
Kind, Tokens saved, Money saved and Attention. Each name opens a native `<details>` inside the row.
That detail contains the full current measurement set as a two-column definition list, including
availability, assumptions, version, considered/applicable/accepted counts, tokens processed,
shares, rates and total latency. Place effective request budget, cost class, average latency and
skipped-budget rate together in that detail. Show the money range, method, basis and price-book
version there. Replace hover-only column help with visible definitions inside the detail. Preserve
the marginal-attribution note.

Requirements touched: UI-002, UI-003, UI-008, UI-009, UI-013 and TC-016 (**within spec**). No
Spec Change Request is needed.

#### Compressors sketch — 1280 px

```text
Tokli        Overview  Compressors  Recent requests  Settings
             Filters: [Last 7 days] [Provider] [Model] [Kind]

Each compressor is credited with what it saved after earlier compressors.

Compressor             On     Kind                    Tokens saved   Money saved   Attention
> JSON minify          yes    lossless · structural         8,100   $0.42 est.    —
> Log filter           no     selective                         —   —             —

(opened row)
  Available: yes                    Effective budget: 25 ms/request
  Cost class: cheap                 Average latency: 0.4 ms
  Skipped for budget: 0.0 %         Tokens read: 20,100 estimate
  ...all remaining existing fields...
  Money: $0.42 estimate; $0.10–$0.74; positional; billed; price book ...
  Assumptions: ...
```

#### Compressors sketch — 360 px

```text
Compressors

Filters
[range              ]
[provider           ]
[model              ]
[kind               ]

Each compressor is credited ...

[internally scrolling compact table]
Compressor | On | Kind | Saved | Money | Attention
> JSON ... | yes| ...  | ...   | ...   | —

Opening “JSON minify” shows a vertical definition list
within the page width; numeric values remain right-aligned.
```

### P4 — Make Recent requests a semantic, complete request list

Add Provider as required by SPEC 016. Keep all current figures and method labels. Replace clickable
rows with a real “View” button in each row; mouse, Enter and Space then work natively. Mark the
selected row with text/`aria-current`, show the detail immediately after the table, and begin the
detail with provider, model and outcome before the unchanged trace. Keep the table in its internal
horizontal scroll container at 360 px.

Requirements touched: UI-002 and UI-008 (**within spec**), plus the approved SPEC 016 Recent
requests page definition (**within spec**). No Spec Change Request is needed.

#### Recent requests sketch — 1280 px

```text
Tokli        Overview  Compressors  Recent requests  Settings

Time        Provider   Model       Outcome       Saved       Forwarded    Money     Overhead  Action
10:42       anthropic  claude-...  compressed    320 est.    8,120 exact  $... est. 7.1 ms    [View]

[Older requests]

Request 01...
anthropic · claude-... · compressed
Saved ... · forwarded input ... · k ...
trace...
```

#### Recent requests sketch — 360 px

```text
Recent requests

[internally scrolling table]
Time | Provider | Model | Outcome | Saved | Forwarded | Money | Overhead | Action
...                                                                    [View]

[Older requests]

Request 01...
anthropic · claude-... · compressed
[wrapped summary]
[wrapped trace]
```

### P5 — Make Settings a single control list with reference text on demand

Put “Lossless only” first, with its current explanation. Move the two exact UI-010 paragraphs,
unchanged byte-for-byte as visible text, into a native `<details>` labelled “What the kinds mean”.
Render compressors as one vertical list separated by rules. Each row shows name, kind, availability,
a stable “Enabled” checkbox label, the lock source when present, and the UI-004 “drops information”
warning when applicable. Keep the exact UI-012 toggle label and warning expanded because it changes
the risk of the adjacent control. Put evaluation, assumptions and version in a native “Evidence and
assumptions” detail. Keep Data retention as a separate final section.

Requirements touched: UI-003, UI-004, UI-005, UI-008, UI-010 and UI-012 (**within spec**). The
approved UI-010 and UI-012 sentences do not change, so no Spec Change Request is needed.

#### Settings sketch — 1280 px

```text
Tokli        Overview  Compressors  Recent requests  Settings

Compressor settings
[Lossless only]  switches off every compressor that drops information
> What the kinds mean

JSON minify                 lossless · structural       [x] Enabled
Available
> Evidence and assumptions
---------------------------------------------------------------------
Log filter                  selective                   [ ] Enabled
Drops information
[ ] Also on Read, Bash, ...
These tools' output is often copied back exactly ... fail.
> Evidence and assumptions

Data
Keep request records for [30] days  [Save]
```

#### Settings sketch — 360 px

```text
Settings

[Lossless only]
switches off every compressor that drops information
> What the kinds mean

JSON minify
lossless · structural
[x] Enabled
> Evidence and assumptions

Log filter
selective · Drops information
[ ] Enabled
[ ] Also on Read, Bash, ...
These tools' output ... fail.
> Evidence and assumptions

Data
Keep records for [30] days
[Save]
```

### P6 — Add deterministic visual evidence without a committed image baseline

Add the screenshot test required by the brief. When `UI_SCREENSHOTS_DIR` is set it writes one PNG
for each of the four pages at 1280×900 and 360×740 in both light and dark colour schemes (16 images),
using the existing synthetic traffic. Images are review artifacts and are never committed. Keep the
test free of network and new dependencies.

Requirements touched: UI-006 and UI-008 (**within spec**). No Spec Change Request is needed.

## 3. Contradictions

No normative contradiction requires an SCR.

The apparent tension between UI-003 (visually distinguish non-lossless kinds) and the brief's
one-accent palette is resolved within spec: explicit kind text, “drops information” wording, font
weight and the single warning accent distinguish SELECTIVE/LOSSY/UNKNOWN without a separate colour
for every kind.

The brief permits secondary detail in native `<details>` while requiring every figure to remain
reachable. P2, P3 and P5 follow that rule; no required datum is removed or renamed.

## 4. Missing behaviour and current conformance gaps

These are presentation gaps in the current implementation, not requests for new product behaviour:

1. Provider is absent from Recent requests (SPEC 016 page definition; F17).
2. Non-dominant overhead groups and p99/max are not reachable (UI-009 / TC-013; F9).
3. Compressor money lacks basis and price-book version (UI-013; F14).
4. Saved time-series values do not visibly expose their per-bucket method (UI-002; F8).
5. The request-detail action is not a native control and is not Space-activatable (brief
   accessibility direction; F18).
6. UI-007 remains legitimately deferred: debug-content mode does not yet exist. This slice does not
   add it.

## 5. Portability concerns

- Continue to use only packaged HTML, CSS and JavaScript with no build step or external resource.
- Use no web font, framework, browser-specific API or OS-specific path.
- Native `<details>`, `<summary>`, `<button>`, `<label>`, `<input>` and `<select>` work on the
  supported Chromium test target and require no polyfill.
- Keep tables inside bounded `.scroll` containers; expanded details must wrap long assumptions,
  lock sources, tool lists and request ids without increasing `documentElement.scrollWidth` at
  360 px.
- Keep explicit light and dark colour variables and verify WCAG AA contrast for body text, muted
  text, focus and warning states in both schemes.
- Screenshot file construction must use `pathlib`, and the output directory is supplied explicitly
  through `UI_SCREENSHOTS_DIR`; no CWD-relative output or personal path is allowed.

## 6. Observability requirements

This slice adds no runtime path, telemetry field, decision or reason code. Therefore the
`TOKLI_OBSERVABILITY.md` §8 items for new spans, decisions, schema fields and privacy scans are not
applicable.

The existing Recent-request trace remains reachable and gains a clearer request summary. No content
is added to the list or detail. UI load and PATCH failures continue to use the existing live status
regions. The completion report must explicitly record that no observability schema or logging change
was made.

## 7. Architectural risks

- **API coupling:** layout changes must render only fields already returned by `/tokli/api`; no
  storage, compressor identity or backend import may enter the bundle (UI-001, ARCH §5).
- **Hidden loss of required data:** moving fields into `<details>` can accidentally omit a metric.
  Tests will enumerate required compressor and overhead fields before visual work begins.
- **Duplicated render paths:** the compact compressor summary and expanded detail must be produced
  from the same registry/metrics row, not from parallel compressor-specific logic.
- **Responsive duplication:** do not create separate desktop and mobile DOM copies. One semantic
  structure is styled responsively, preventing mismatched values and duplicate focus targets.
- **No new seam:** this is three static files and one browser-test module. No component framework,
  design system, router, registry or dependency is justified.
- **No ADR:** the proposals change no dependency, persistent format, public contract, protocol or
  portability characteristic.

## 8. Product questions for the human

1. **Should secondary totals on Overview be closed by default?** Recommendation: **yes**. Saved
   tokens, money and saving percentage remain immediately visible; request count, original and
   forwarded totals remain one native disclosure away. This is the main prioritisation decision in
   P2.
2. **Should each compressor's full measurement set be closed by default?** Recommendation: **yes**.
   The compact row answers on/off, kind, saving and attention at a glance; every current field stays
   reachable in that compressor's native detail. This is the main density decision in P3.
3. **Should the exact kind explanations be closed by default in Settings?** Recommendation:
   **yes**. They remain visible text when opened and unchanged word-for-word, while the safe shortcut
   and toggles move above the fold. This is the main control-priority decision in P5.

Approval of the proposals with the recommended answers is sufficient; none requires a Spec Change
Request. If the human instead wants any approved figure removed, an approved wording changed, or an
API field added, that alternative must first be written as an SCR.

## 9. Implementation decisions

Subject to Gate 1 approval, the agent will decide and record ordinary implementation details:

1. Preserve stable hooks such as `data-tab`, `data-panel`, `data-card`, `data-compressor` and
   `data-toggle` where their meaning still fits, to avoid unnecessary test churn.
2. Use native disclosure controls; do not implement custom accordion state or animation.
3. Keep one DOM structure for both viewport sizes and both colour schemes.
4. Use tabular numerals and right alignment for numeric columns; put units in headers or labels.
5. Use the existing API reason codes with the existing plain-language mapping; unknown codes remain
   visible rather than being hidden.
6. Keep the existing chart implementation small and dependency-free; add accessible/tabular data
   rather than introducing a chart library.
7. Use only one accent token for selected controls, focus and warnings. Non-lossless meanings always
   include text, so colour is never the sole cue.

## 10. Test plan

Tests are derived before implementation and must first fail for the expected markup or behaviour
change, not for an import, fixture or browser-installation error.

### Existing tests to update only where approved markup changes

| Test | Planned change and reason |
|---|---|
| `test_ui_renders_method_labels` | Open native details before enumerating figures, and include saved time-series values. The UI-002 assertion is strengthened, not weakened. |
| `test_ui_cost_card_shows_estimate_range_and_method` | Follow the new Overview hierarchy while preserving assertions for estimate, range, method, basis and price book. Add separate caveat-line assertions. |
| `test_ui_compressor_money_column` | Follow the compact-row/detail structure and add assertions for basis, range, method and price-book version required by UI-013. |
| `test_ui_shows_kind_equivalence_and_assumptions` | Open compressor detail before checking assumptions; keep exact equivalence assertions. |
| `test_ui_overhead_target_is_reference_line` | Follow the reorganised Overview and keep the exact “target (not a limit)” and no pass/fail assertions. |
| `test_ui_request_detail_renders_trace` | Activate the new native View button instead of clicking a row; keep trace assertions. |
| `test_ui_usable_at_360px` | Keep the page-width assertion and add assertions that every intentionally wide table scrolls only inside its wrapper. |
| `test_ui_toggle_patches_config` | Update locators only if necessary; keep PATCH, response re-render and persisted-config assertions unchanged. |
| `test_ui_shows_equivalence_assumptions_and_eval_status` | Open “Evidence and assumptions”; keep exact status and assumption assertions. |
| `test_ui_policy_explanations_text` | Open “What the kinds mean”; keep both approved strings exact and complete. |
| `test_ui_lossless_only_shortcut_switches_off_non_lossless` | Update layout locator only; keep the single PATCH and “drops information” assertions. |
| `test_ui_locked_settings_show_source` | Update layout locator only; keep disabled state and exact source assertions. |
| `test_ui_verbatim_opt_in_toggle` | Update layout locator only; keep label, exact warning, independent setting and PATCH assertions. |

No integration, contract or packaging assertion needs weakening. The static bundle lint, offline
resource scan, explicit content types, package contents and dashboard route tests remain unchanged.

### Tests to add

| Proposed test | Requirement or finding covered |
|---|---|
| `test_ui_filters_are_only_on_metrics_pages` | P1 / F1: filters are visible on Overview and Compressors, hidden on Recent and Settings, and retain values. |
| `test_ui_overview_prioritises_savings_and_keeps_totals_reachable` | P2 / F6–F7: DOM/heading order puts saved tokens and money first; secondary totals and method legend remain reachable. |
| `test_ui_timeseries_values_show_methods` | UI-002 / F8: every bucket value in the disclosure has an adjacent method or an unavailable reason. |
| `test_ui_all_overhead_groups_and_percentiles_are_reachable` | UI-009 / TC-013 / F9: every API group and bucket exposes n, p50, p95, p99 and max; target remains reference-only. |
| `test_ui_compressor_summary_and_full_details` | UI-009 / TC-016 / F12–F16: compact row fields and every existing detailed metric are present; budget, cost class, average latency and skipped-budget rate are grouped. |
| `test_ui_recent_requests_show_provider_and_native_detail_button` | SPEC 016 page definition / F17–F20: provider is shown; a real button has an accessible name and opens the correct detail with keyboard activation. |
| `test_ui_focus_is_visible_in_both_colour_schemes` | UI-008 / F4: keyboard focus has a non-zero visible outline/indicator in light and dark schemes. |
| `test_ui_settings_primary_controls_and_disclosures` | UI-003/UI-004/UI-010/UI-012 / F21–F25: shortcut and stable Enabled labels precede secondary disclosures; approved texts remain reachable. |
| `test_ui_screenshots` | Brief phase 2 / UI-008: conditional 16-image capture for four pages × two viewports × two colour schemes, using synthetic traffic and `UI_SCREENSHOTS_DIR`. |

### Verification after implementation

Run the full commands required by `AGENTS.md` §3, including the browser suite with
`RUN_BROWSER_TESTS=1`, plus screenshot generation in a temporary output directory. Record counts,
skips and any environment limitation exactly in the completion report.

Phase-1 environment note: the existing browser suite was attempted with a repository-local pytest
base temp. It did not execute UI assertions because Playwright's Chromium executable is absent in
this environment. Result: 7 failed and 8 errors, all ending at `BrowserType.launch` with “Executable
doesn't exist”; this is not evidence of current UI conformance or non-conformance.

## Gate 1 record

2026-10-05 · Human approval words: “approvo gate 1 con le propooste raccomandate” · The three
recommended answers in §8 are approved. Spec delta: SPEC 016 records S6.5 approval; no requirement,
acceptance criterion or approved wording changed.
