# S6.6 — Completion report

## Requirements implemented

- **SPEC 018 PT-004** as changed by S6.6 SCR-001: CPython 3.14 joins the supported set.
- **Deferred:** none.

## Changes

- **`pyproject.toml`:** `requires-python = ">=3.11,<3.15"`, the 3.14 classifier, version 0.1.1.
- **CI:** the matrix gains 3.14 (12 test jobs). The cross-job identity check now expects 12 snapshots (it
  counted exactly 9, and failed on the first run, 37895427645).
  - **Deviation from the SCR text:** the single-version steps (metrics and E9 benchmarks, and the
    E9 artifact upload) stay on 3.13. They are compared with the committed E9 baseline, which was
    recorded on 3.13, so moving them would compare different interpreters.
  - The browser job keeps its own interpreter.
- **Typing fix,** needed by the newer mypy/pydantic releases on every Python version:
  - `_is_model` in `tokli.config.schema` is now a `TypeGuard[type[BaseModel]]`;
  - a `# type: ignore` that this made unnecessary is gone;
  - there is no behaviour change, and mypy (strict) is clean with mypy 2.3.1 and 2.4.0.
- **Documents updated to 3.11–3.14:**
  - spec and decision records: SPEC 018, ADR 0001 (amendment), ADR 0005;
  - process: `CLAUDE.md` §9, `AGENTS.md`;
  - scope and architecture: `TOKLI_SCOPE.md`, `TOKLI_ARCHITECTURE.md`;
  - user documents: README, `docs/GETTING_STARTED.md` (install from `v0.1.1`),
    `docs/DEVELOPMENT.md`;
  - the roadmap entry.

## Tests and evidence

**Python 3.14.3**, fresh virtual environment, before the change (SCR §2):
- every dependency installs from wheels;
- 792 passed, 10 skipped (browser tests included);
- 7 import contracts kept;
- 1 mypy error, fixed here.

**Python 3.11** after the change: 765 passed, 10 skipped (no browser tests); ruff, mypy and
`lint-imports` clean.

**CI:** run 37896537774 (commit eaca361): all 12 jobs green; cross-job identity check green (12
snapshots).

## Measured performance

Not affected: no runtime code changed.

## Known limitations

None new. A future Python version is added the same way: test it, then widen the bound.

## Gate 2 record

- **Date:** 2026-10-09.
- **The human's words:** "vai e pusha".
