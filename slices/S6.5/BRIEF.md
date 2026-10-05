# S6.5 — Dashboard review: brief for the implementing agent

**Requested by the human on 2026-10-05.** The work is done by an OpenAI Codex agent. Read
`AGENTS.md` and `CLAUDE.md` first: their process and rules apply in full.

## 1. Goal

Make the dashboard **simple**: a person who uses a coding agent opens it and understands, in a
few seconds:
- what Tokli saved, in tokens and money;
- whether anything needs attention;
- where to switch compressors on or off.

**It must look like a plain, careful tool written by a person, not like generated UI.** Function
first, few elements, plain words.

Behaviour does not change. This is a review of presentation, wording and layout.

## 2. What exists today

**Files:**
- static files in `src/tokli/ui/`: `index.html` (105 lines), `app.js` (586), `style.css` (183);
- no build step, no framework, no external resources;
- served at `/tokli/` and fed only by the JSON API under `/tokli/api` (SPEC 015).

**Pages:**
- **Overview:**
  - cards for requests, original, forwarded and saved tokens, saving % and money saved;
  - a legend of methods;
  - a table of saved tokens per compressor;
  - a saved-tokens chart;
  - an overhead chart with a target line.
- **Compressors:** one table of about 20 columns per compressor.
- **Recent requests:** a table, and a detail view with the trace.
- **Settings:**
  - compressor toggles;
  - the "Lossless only" shortcut;
  - the explanation of kinds;
  - the verbatim opt-in;
  - data retention.
- **Header:** a page switcher, plus filters (range, provider, model, kind) shown on every page.

**Tests:** `tests/ui/test_dashboard.py` (Playwright, headless Chromium) and
`tests/integration/test_metrics_api.py` (API contract and content types).

**Normative text:** SPEC 016 (UI-001…UI-013, AC-UI-1…AC-UI-5), SPEC 015 (the API it reads),
SPEC 013 (what the figures mean). Explanations for wording: `TOKLI_COMPRESSORS.md` §11 and
`TOKLI_TELEMETRY_AND_COST.md`.

## 3. Design direction: simple, not "AI-styled"

**Do:**
- **Type and colour:**
  - the system font stack and the browser's default sizes, with a clear type scale of 3–4
    sizes at most;
  - one neutral palette and **one** accent colour, used only for interactive elements and
    warnings;
  - light and dark themes from `prefers-color-scheme` (UI-008).
- **Tables:** plain tables with right-aligned numbers, units in the column header, and no
  zebra or borders beyond what reading needs.
- **What appears first:**
  - the few numbers that matter most;
  - secondary detail behind a native `<details>`/`<summary>` or on its own page, never
    removed (see §4).
- **Wording:**
  - plain sentences, sentence case, the same word for the same thing everywhere;
  - a value that is unknown is "—" with its reason (UI-002).
- **Accessibility:**
  - real controls (`<button>`, `<label>`, `<select>`);
  - visible focus and keyboard use;
  - colour contrast of at least WCAG AA.

**Don't:**
- gradients, glass or blur effects, large shadows, glow, neon or purple-blue "tech" palettes;
- emoji, decorative icons, illustrations, sparkles, hero banners;
- marketing or cheerful copy ("Supercharge…", "Awesome!", exclamation marks);
- rounded "pill" styling everywhere, oversized radius, oversized KPI tiles, decorative
  sparklines;
- animations and transitions, except a functional one under `prefers-reduced-motion: no-preference`;
- utility-class soup, CSS frameworks, JS frameworks, web fonts, CDNs, a build step, or any new
  dependency.

## 4. Constraints that must still hold (do not break, do not reinterpret)

**SPEC 016:**
- **UI-001:** all data comes from `/tokli/api`, with no compressor-specific logic. AC-UI-1
  lints the bundle for compressor ids.
- **UI-002:** every token figure shows its method label; every money figure shows "estimate",
  its range and method; an unknown value shows "—" with its reason.
- **UI-003:** kind **and** equivalence, assumptions and evaluation status; non-lossless kinds
  are visually distinct.
- **UI-004, UI-010, UI-012:** the "Lossless only" shortcut and **the exact explanation texts**
  of UI-010 and UI-012. They are approved wording: not one word may change without a Spec
  Change Request.
- **UI-005:** locked settings are disabled and show their source.
- **UI-006, AC-UI-4:** static files from the package; no external network resource; the
  dashboard works offline.
- **UI-007:** the debug-content banner, when that mode exists.
- **UI-008:** usable at 360 px wide, with no horizontal page scroll; respects
  `prefers-color-scheme`.
- **UI-009:**
  - the overhead target is a reference line labelled "target (not a limit)", never pass or
    fail;
  - the Compressors page shows `cost_class`, average latency and the `skipped_budget` rate
    next to the effective budget.
- **UI-011, AC-UI-5:** served at `/tokli/` with explicit content types.
- **UI-013:** money with its range, method in plain words, basis label and price-book version,
  plus the caveats when they are non-zero.

**Elsewhere:**
- **No API change.** The JSON API, its schemas (`tests/contract/api/`) and the backend stay as
  they are. If a simpler page truly needs an API change, write it in the spec review as a
  question for the human.
- **Every figure the specs ask to show stays reachable.** It may move to a secondary place,
  never disappear. Anything in SPEC 016's page table that you want to drop or rename needs a
  Spec Change Request.

## 5. Process (the gates are the human's)

### Phase 1 — review, no code

Write `slices/S6.5/SPEC_REVIEW.md` (template in `CLAUDE.md` §7). It must contain:
1. **Findings** for each page: what is unclear, crowded, inconsistent, inaccessible or looks
   generated. Each finding cites the element (file and selector) and states why it matters to
   a user.
2. **Proposals, numbered.** Each says what changes, and shows a plain-text sketch of the new
   layout of every page you change, at 1280 px and at 360 px.
3. **For each proposal:**
   - the requirements it touches, marked **within spec** or **needs a Spec Change Request**;
   - for the latter, draft `slices/S6.5/SCR-<nnn>-<slug>.md` per `CLAUDE.md` §4.
4. **Product questions** for the human, each with your recommended answer.
5. **The test plan:** which tests change and why, and which are added.

Then **stop** and wait for the human's explicit approval (Gate 1). Make no code change before
it.

### Phase 2 — implementation, after Gate 1

- Work on a branch `s6.5-dashboard-review`. Commit only when the human asks.
- **Tests first** for anything with observable behaviour: new structure, new controls, the
  places where figures now appear. Run them and show that they fail for the right reason.
- **Existing tests:**
  - change one only where it asserts markup that the approved proposals change;
  - never weaken an assertion that encodes a requirement (method labels, reasons, 360 px, the
    target label, exact texts, offline, content types);
  - list every changed test and why in the completion report.
- **A screenshot test** that writes, when `UI_SCREENSHOTS_DIR` is set, a PNG of each page:
  - at 1280×900 and at 360×740;
  - in light and dark colour scheme;
  - from the same synthetic traffic the browser tests use.

  The images are **not** committed.

### Phase 3 — verification

- Run every check in `AGENTS.md` §3, including `RUN_BROWSER_TESTS=1 pytest tests/ui`.
- Write `slices/S6.5/COMPLETION_REPORT.md` (template in `CLAUDE.md` §7). Add:
  - a before/after list per page;
  - the screenshot command;
  - the list of changed tests.
- Then **stop for the human verification (§6).** The slice is complete only after the human's
  explicit acceptance.

## 6. Human verification (Gate 2)

The human goes through `slices/S6.5/HUMAN_REVIEW.md`:
- on the screenshots;
- on the live dashboard with their own data (`tokli serve`, then `http://127.0.0.1:8787/tokli/`).

Fix what they report, then ask again. Record the acceptance words and date at the end of the
completion report.

## 7. Out of scope

- New figures, new endpoints, new pages beyond what SPEC 016 lists (the Diagnostics page belongs
  to S9).
- Any change to compression, telemetry, pricing or configuration behaviour.
- Branding: logo, colour identity, fonts.
