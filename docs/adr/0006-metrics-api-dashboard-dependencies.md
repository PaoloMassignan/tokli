# ADR 0006 — Metrics API and dashboard: dependencies and boundaries

Status: accepted (S3, 2026-10-03; approved at S3 Gate 1, decisions P5, P7, P9) · Related:
SPEC 015, SPEC 016, ADR 0001, ADR 0004

## Context

S3 adds the metrics API and a static dashboard. Three needs are not met by the existing
dependencies (ADR 0001):

- time-zone-aware day buckets (API-010) work on Windows only with an IANA time-zone database,
  which Windows does not ship;
- the API contract tests (AC-API-1) need a JSON Schema validator;
- the dashboard's method-label rule (UI-002, AC-UI-2) can only be checked in a real browser.

SPEC 015 also requires that the API layer use only `tokli.app` use cases (API-008).

## Decision

- **Runtime:** `tzdata` (pure data, maintained by the Python core developers, Apache-2.0).
  `zoneinfo` uses the system database where one exists and falls back to `tzdata`, so every OS
  resolves the same names.
- **Development:** `jsonschema` for the contract tests (`tests/contract/api/*.schema.json`).
- **Browser tests:** `playwright` as a separate optional extra (`.[ui-test]`), with headless
  Chromium. It runs in **one** CI job (Ubuntu, Python 3.12) with `RUN_BROWSER_TESTS=1`, and
  locally only when installed. The other jobs run every non-browser test.
- **Boundaries:**
  - the SQL for metrics lives in `tokli.telemetry.queries`;
  - the use cases live in `tokli.app.metrics` (`MetricsQuery`);
  - a new import contract forbids `tokli.http.app` (the routes) from importing `tokli.telemetry`
    directly;
  - the dashboard is static files in `tokli/ui/`, served by `tokli.http`, and reads only
    `/tokli/api`.
- **Host check (API-009):** every `/tokli/*` route answers 403 to a `Host` that is not the bound
  address and port. When bound to loopback, `localhost`, `127.0.0.1` and `[::1]` with the bound
  port are accepted. When bound to a wildcard address (`0.0.0.0` or `::`, only possible with
  `--allow-remote`), only the port can be checked.

## Alternatives considered

- **UTC-only time zones:** no dependency, but day buckets would be wrong for every user outside
  UTC. Rejected (API-010).
- **Hand-written shape checks instead of JSON Schema:** less precise and harder to review.
  Rejected.
- **No browser test:** the method-label rule would rest on reading JavaScript. Rejected at Gate 1.
- **Browser tests in all 9 jobs:** about 9 × 150 MB of browser downloads per run for no extra
  coverage of a static page. Rejected.

## Consequences

- One new runtime dependency (`tzdata`), small and data-only. The packaging test checks that a
  clean install resolves `Europe/Rome`.
- Contributors without Playwright skip the browser tests; CI always runs them in one job.
- The import contract makes API-008 checkable.
