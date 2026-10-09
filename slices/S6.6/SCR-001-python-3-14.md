# S6.6 SCR-001 — Support CPython 3.14

Status: **approved 2026-10-09** ("approvo"). Asked by the human: they were asked to use Python
3.14.7.

If approved, the change is carried out as a small slice **S6.6** (roadmap entry added on approval).
Approval of this SCR counts as Gate 1. Gate 2 stays as usual.

## 1. Affected requirements and decisions

- **SPEC 018 PT-004** (approved S0): "THE supported platform set SHALL be exactly the CI matrix:
  Windows, Linux, macOS × CPython 3.11, 3.12, 3.13. `requires-python` SHALL match."
- **SPEC 018 MD-18:** `requires-python` equals the CI matrix. Unchanged in principle; the matrix
  grows.
- **ADR 0001** (build tooling): `>=3.11,<3.14` and the CI matrix {3.11, 3.12, 3.13}.
- **ADR 0005:** its portability note names "CPython 3.11–3.13".
- **`CLAUDE.md` §9 and `AGENTS.md` §3:** "CPython 3.11–3.13".

## 2. Evidence (2026-10-09, Windows, CPython 3.14.3)

1. **Installation.** `pip install --ignore-requires-python -e ".[dev,ui-test]"` in a fresh
   virtual environment: every dependency installs from a prebuilt wheel and nothing is compiled.
   This covers pydantic 2.14 / pydantic-core 2.50, tiktoken 0.14, PyYAML 6.0.3, starlette 0.52,
   uvicorn 0.54, httpx 0.28 and playwright 1.63.
2. **Full suite, browser tests included:** **792 passed, 10 skipped** (the environment-gated
   ones, as on 3.11). `lint-imports`: 7 contracts kept.
3. **mypy: 1 error,** `src/tokli/config/schema.py:236`: `field.annotation` is `TypeForm[Any]`,
   not `type[BaseModel]`.
   - **Not caused by 3.14:** it also appears with `--python-version 3.11`. It comes from the
     newer type stubs (mypy 2.4.0 with pydantic 2.14).
   - **Consequence:** CI would hit it on every Python version as soon as it installs those
     releases.
   - **Fix:** `_is_model` becomes a `TypeGuard[type[BaseModel]]`, with no behaviour change.

**3.14.x patch releases are compatible by CPython's policy.** The check on 3.14.3 therefore
stands for 3.14.7. CI uses the latest 3.14 that GitHub provides.

## 3. Why the requirement should change

The human needs 3.14. The evidence shows Tokli works on it unchanged, apart from a typing fix
needed anyway. PT-004's principle stays: supported = tested = installable.

## 4. Proposed change

**PT-004** becomes:

> PT-004 | THE supported platform set SHALL be exactly the CI matrix: Windows, Linux, macOS ×
> CPython 3.11, 3.12, 3.13, 3.14. `requires-python` SHALL match. (S6.6 SCR-001.)

**Implementation:**
- `requires-python = ">=3.11,<3.15"`, plus the 3.14 classifier;
- the CI matrix gains `"3.14"` (12 test jobs);
- the identity check covers all 12;
- the single-version steps (benchmarks, the browser job) move from 3.13 to 3.14;
- ADR 0001 gets an amendment, and ADR 0005's note says 3.11–3.14;
- `CLAUDE.md` §9, `AGENTS.md` §3 and `docs/GETTING_STARTED.md` say 3.11–3.14;
- the `_is_model` typing fix.

**Not proposed:** removing the upper bound (`>=3.11` alone). A future 3.15 would then install
without ever having been tested, which is what PT-004 and MD-18 exist to prevent. A new Python
version is added the same way: test it, then widen the bound.

**Other dependencies need no relaxing.** Their bounds are minimums with a cap on the next major
version (for example `pydantic>=2.7,<3`). The latest releases already install on 3.14.

## 5. Impact on tests

- No test changes. The whole suite runs on the new matrix entry.
- The typing fix is checked by `mypy` (strict) on every job.

## 6. Impact on architecture

None. No module, dependency or contract changes.

## 7. Compatibility and migration

- **What changes:** an installation on 3.14 is accepted.
- **What does not change:** 3.11–3.13 users, the persisted schema, config keys and
  `config_hash`.
- **Users today:** someone who installed on 3.11–3.13 changes nothing. A 3.14 user installs
  the next release (v0.1.1).
