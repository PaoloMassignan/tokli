# ADR 0001 — Build, tooling and runtime dependencies

Status: accepted (S0, 2026-09-29) · Related: TOKLI_ARCHITECTURE.md §9, `slices/S0/SPEC_REVIEW.md` §6

## Context

S0 creates the Python package. Adding persistent third-party dependencies and choosing the build
layout are significant decisions (`CLAUDE.md §6`). They constrain every later slice and
portability (PT-004, MD-19).

## Decision

| Concern | Choice | Why |
|---|---|---|
| Build backend | `hatchling` (≥ 1.27, SPDX `license` field) | small, standard, no custom build steps |
| Layout | `src/tokli`, import root `tokli` | the source tree cannot be imported by accident from the working directory (MD-04, MD-19) |
| Python | `>=3.11,<3.15`, equal to the CI matrix (PT-004) | an unsupported interpreter fails at install time (MD-18) |
| Config validation | `pydantic` v2, strict JSON-mode validation | already chosen in ARCH §9; strict mode rejects implicit coercions (CF-012) |
| Config file | `PyYAML`, safe loader with duplicate-key detection and YAML 1.2 booleans only | the config file is YAML (SPEC 017); strictness is added by Tokli (CF-012) |
| CLI | stdlib `argparse` | no dependency needed for three commands |
| Tokenizer download | stdlib `urllib.request` | only the explicit `tokli setup tokenizers` command uses the network (PT-003) |
| Tokenizer library | **not a dependency in S0** | S0 only provisions and verifies files; counting (`tiktoken`) arrives with its first consumer in S1 (`CLAUDE.md §5`) |
| Dev tools | `pytest`, `ruff`, `mypy --strict`, `import-linter`, `types-PyYAML` | TOKLI_TEST_STRATEGY §1, ARCH §5 |
| CI | GitHub Actions, {Windows, Ubuntu, macOS} × {3.11, 3.12, 3.13, 3.14} on every push and pull request (3.14 added by S6.6 SCR-001) | public repository, no minute limits (S0 review P1) |

## Alternatives considered

- `platformdirs` for directory resolution: rejected. The resolver is about 30 lines, and MD-07
  asks for a small internal one whose output is fully specified in SPEC 017.
- `click`/`typer` for the CLI: rejected for now. `argparse` is enough, and a new dependency
  needs a reason.
- `tomllib`/TOML config: rejected. SPEC 017 names YAML.

## Consequences

- Runtime dependencies in S0: `pydantic`, `PyYAML`. Each new runtime dependency needs its own ADR.
- `tiktoken` is added in S1 by ADR, with the pinned files that S0 already provisions.
- Tokenizer SHA-256 values are pinned in `tokli.tokens.catalog`. They were verified against the
  published files and the values declared in the `tiktoken` source.

## Amendment 2026-10-09 (S6.6 SCR-001)

CPython 3.14 joins the supported set: `requires-python = ">=3.11,<3.15"` and a fourth CI
column.
- **Evidence:** every dependency installs on 3.14 from prebuilt wheels, and the full suite
  passes.
- **The upper bound stays:** a Python version is supported only once CI tests it (PT-004,
  MD-18).
- **The benchmarks** keep running on 3.13, so that they stay comparable with the committed E9
  baseline.
