# ADR 0009 — Runtime configuration changes and packaged evaluation records

Status: accepted (S4, 2026-10-03; approved at S4 Gate 1, decisions P3, P4, P5, SCR-001) · Related:
SPEC 015 API-005…API-007, SPEC 017 CF-001, CF-005, CF-009, SPEC 016 UI-003

## Context

Until S3 the configuration was fixed at startup, and the proxy held one `Services` built from
it. S4 lets the dashboard switch compressors and change the retention period while Tokli runs.
It also shows each compressor's evaluation status, whose records live in the repository
(`evals/records/`), not in the installed package.

## Decision

- **Layer 5, UI overrides:** `<data dir>/ui-overrides.yaml`, read strictly like the config file.
  It may set only `ui_editable` keys (`compressors.<id>.enabled`, `telemetry.retention_days`).
  A key that env or the CLI sets is **locked**: the override is ignored, the key is reported with
  its source, and a PATCH on it answers 409.
- **Snapshots:** a `Runtime` in `tokli.app.runtime` holds the current snapshot: the effective
  config plus the pipeline and engine built from it. A request reads `runtime.current()` once and
  keeps it to the end (CF-005). A PATCH, through `ConfigService`:
  - validates the change;
  - writes the overrides file atomically (a temporary file, then `os.replace`);
  - builds a new snapshot, reusing the loaded tokenizers;
  - swaps it under a lock.

  A failed write answers 500 and changes nothing.
- **Evaluation records in the package:** the wheel build copies `evals/records/*.yaml` to
  `tokli/_eval_records/` (hatch `force-include`). At run time Tokli reads that folder, or, in a
  development checkout, the repository's `evals/records/`. A record whose version differs from the
  compressor's is reported as `outdated`.
- **Origin check (API-006):** a mutating request with an `Origin` header that is not Tokli's own
  origin answers 403. The host check (API-009) still applies to every `/tokli/*` request.

## Alternatives considered

- **Restarting Tokli on every change:** simple, but it drops requests in flight and loses the
  in-memory traces. Rejected.
- **Mutating the live config object:** breaks CF-005 (one consistent snapshot per request).
  Rejected.
- **Putting the records inside the source package:** QE-016 places them in `evals/records/`,
  next to the reports. Copying them at build time keeps one source.

## Consequences

- **Tests:**
  - the precedence and locking rules;
  - an atomic snapshot test with a request in flight;
  - the 409, 400 and 403 cases;
  - the wheel contains the records.
- **Portability:** `os.replace` fails on Windows while another process holds the target open;
  the PATCH then answers 500 and the old overrides stay in force.
