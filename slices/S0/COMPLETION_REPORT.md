# S0 — Completion report

Slice: **S0 — Walking skeleton (no proxying yet)** · Branch `s0-walking-skeleton` (not merged)
Status: **awaiting Human Gate 2**

## Requirements implemented

| Spec | Requirements |
|---|---|
| 017 configuration | CF-001 (layers 1–4), CF-002 (`tokli config show`), CF-003, CF-004, CF-005, CF-006, CF-008, CF-011, CF-012 |
| 008 token measurement | TM-006, TM-007, TM-010; `tokens.default` / `tokens.model_map` schema |
| 018 portability & diagnostics | PT-003 (setup command only), PT-004, PT-005 (S0 subset), PT-007, PT-008 (invalid config, unwritable data dir, missing tokenizer), PT-010, PT-011 (MD-02, 04, 05, 07, 08, 16, 18, 19, 20, 27), PT-012 |
| Architecture §5 | layers contract `tokli.cli > tokli.app > tokli.config \| tokli.tokens` |

Deferred as approved (`SPEC_REVIEW.md`): UI override layer (S4), TM-001/TM-002/TM-008
(S1, first counting consumer), CF-007/CF-009/CF-010, other PT-005 fields, port-in-use (S1).

## Tests and evidence

- **CI run 36627825333** on `s0-walking-skeleton`
  (https://github.com/PaoloMassignan/tokli/actions/runs/36627825333): all 9 jobs
  {Windows, Ubuntu, macOS} × {3.11, 3.12, 3.13} green. **63 passed, 0 skipped** in each job,
  including the real clean-venv install test and the doctor snapshot with the real, provisioned
  tokenizer.
- **Exit criterion (AC-PT-7):** the job "Doctor snapshot identical in all 9 jobs" compared the
  9 normalized snapshots and found them identical.
- Every job also passed `ruff check`, `ruff format --check`, `mypy --strict` (15 source files,
  0 issues) and `lint-imports` (1 contract kept, 0 broken).
- Locally (Windows, CPython 3.11.8): the same 63 tests pass with
  `TEST_TOKLI_PROVISIONED_DATA_DIR` and `RUN_PACKAGING_TESTS=1`. Without them, 61 pass and 2 are
  skipped.
- **RED was verified before GREEN:** 54 tests failed with `NotImplementedError` against
  signature-only stubs, with no import or collection errors. The 7 that passed checked properties
  that were already true of the skeleton (import contracts, catalog pins, no dotenv, no CWD paths,
  no developer paths, import without side effects, checklist tests present).
- **Tokenizer pins:** SHA-256 of `o200k_base` and `cl100k_base` verified against the files
  downloaded on 2026-09-29 and against the hashes declared in the tiktoken 0.14.0 source.
- Traceability: every S0 requirement row lists its tests (`TOKLI_TRACEABILITY.md`).

## Architecture changes

- New modules: `tokli.config` (schema, loader, paths, strict YAML, errors), `tokli.tokens`
  (catalog, file checks), `tokli.app` (doctor, setup tokenizers), `tokli.cli`.
- **ADR 0001** (`docs/adr/0001-build-tooling-and-dependencies.md`): hatchling, `src/` layout,
  runtime dependencies `pydantic` + `PyYAML` only, stdlib `argparse` and `urllib`, and no
  `tiktoken` until S1.
- No abstractions without a second implementation (`CLAUDE.md §5`): the loader, the tokenizer
  check and doctor are concrete. `setup_tokenizers` takes a `fetch` function and a `catalog`
  parameter. These are test seams only, with no plug-in mechanism.
- Implementation decision within the spec: a layer that sets a key replaces its whole value (for
  example `tokens.model_map` is never merged across layers). This is the direct reading of CF-001.

## Measured performance

S0 has no request path, so the overhead targets (TOKLI_TEST_STRATEGY §8) do not apply yet.
Reported only: `tokli doctor` takes a median of 288 ms and at most 308 ms over 10 runs (Windows,
3.11, with a provisioned tokenizer). That includes interpreter start-up and hashing the 3.6 MB
tokenizer file. CI test suites take 6–8 s on Linux/macOS and 12–17 s on Windows.

## Observability evidence (`TOKLI_OBSERVABILITY.md §8`)

| Checklist item | S0 |
|---|---|
| Spans with durations | N/A: no request path until S1 |
| Reason codes | N/A: no forwarding decisions yet |
| Telemetry fields | N/A: no telemetry until S1 |
| Credential and content scans | `test_doctor_never_prints_secrets` (canary provider keys in the environment); doctor prints only schema settings, paths and hashes |
| Diagnosability | every failure prints `error: <cause>` and `fix: <fix>` (`test_invalid_config_fails_clearly`); doctor shows each setting's source |

## Known limitations

- **Windows 11 is reported as "Windows 10"** by doctor on Python 3.11 (a CPython `platform`
  limitation that 3.12 corrects). It affects only the non-normalized report.
- **Read-only working directory** (a fresh-machine scenario) is covered as "nothing is written to
  the CWD" (`test_behaviour_independent_of_cwd`). The CWD is not actually made read-only, because
  that cannot be done portably on Windows.
- **Deprecation warning:** GitHub warns that `actions/*@v4`/`@v5` still target Node.js 20. The
  jobs pass. An upgrade of the action versions is worth doing when newer majors are confirmed.
- Tokenizer files come from `openaipublic.blob.core.windows.net`. If that location changes, setup
  fails with a clear message and `--from-file` still works.

## Process deviations (reported honestly)

- The S0 spec delta was already included in the first public commit (`5a9693d`), marked
  "awaiting confirmation", before the product owner confirmed it. I had said it was still local.
  The delta was confirmed later ("Approvo s0") without changes.
- Ruff 0.16 also reformatted Python snippets inside two Markdown documents. The change was
  reverted before any commit, and ruff now excludes `*.md`.

## Unresolved questions

None blocking. Carried forward: C2/C3 for the S1 spec review, Q17 (S4), the SPEC 019 age-rule
ambiguity (S8).

## Gate 2 record

_(pending)_
