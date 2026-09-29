# S0 — Spec review

Slice: **S0 — Walking skeleton (no proxying yet)** (`TOKLI_ROADMAP.md`).
Status: **Human Gate 1 passed 2026-09-29.** Implementation in progress.

## Scope

**Roadmap content.** Package `tokli` with `pyproject.toml` (ruff, mypy --strict, import-linter), a
CI matrix {Windows, Ubuntu, macOS} × {3.11, 3.12, 3.13}, `tokli.config` (schema, precedence,
effective config with sources), data/config directory resolution, the tokenizer provisioning
decision (Q7) and loader, and `tokli doctor` (version, Python, platform, paths, effective config,
tokenizer status). Exit: `tokli doctor` gives the same output (minus paths) on all three OSes in CI.

**Requirements in scope (proposed; see P5):**

| Spec | In S0 | Deferred (slice) |
|---|---|---|
| 017 configuration | CF-001 (layers 1–4), CF-002 (`tokli config show`; API part later), CF-003, CF-004, CF-005, CF-006, CF-008 | CF-001 UI layer (S4), CF-007 (first optional capability), CF-009 (S4), CF-010 (S5 with inject mode) |
| 008 token measurement | TM-006, TM-007, `tokens.default` / `tokens.model_map` schema and validation | TM-001, TM-002 selection, TM-008 (S1, first counting consumer); TM-003…TM-005, TM-009 (S1–S2) |
| 018 portability & diagnostics | PT-003 (setup command only), PT-004, PT-005 (S0 subset), PT-007, PT-008 (invalid config, unwritable data dir, missing tokenizer), PT-010, PT-011 rows MD-02, MD-04, MD-05, MD-07, MD-08, MD-16, MD-18, MD-19, MD-20, MD-27 | PT-005 remainder (with each field's slice), PT-006 (S9), PT-008 port-in-use (S1), PT-009 (per compressor), other MD rows |
| Architecture §5 | import contracts for `tokli.config`, `tokli.tokens`, `tokli.app`, `tokli.cli` | other modules as they appear |

## 1. Ambiguities

| # | Where | Question | Proposed reading |
|---|---|---|---|
| A1 | CF-001, AC-CF-1 | Precedence has 5 layers, but the UI layer belongs to S4 (SPEC 017 status line). | S0 implements layers 1–4. AC-CF-1's UI part is tested in S4. |
| A2 | Roadmap S0 lists TM-002 | TM-002 selects a tokenizer *per request*. S0 has no requests. | S0 validates `tokens.model_map` and `tokens.default` in the schema. Selection is implemented in S1. |
| A3 | TM-006 "at startup" | S0 has no `serve`, so there is no startup. | In S0, `tokli doctor` checks the tokenizer and fails (exit 1) with TM-006's message when it is missing. `serve` inherits the same check in S1. |
| A4 | PT-005 | The full doctor field list includes things that do not exist yet (listen port, upstreams, auth, registry, telemetry DB, debug-content). | S0 doctor prints only the roadmap subset. Each later slice adds its fields. |
| A5 | CF-008 "and the config dir likewise" | The flag and variable names for the config dir are not named. | `--config-dir` → `TOKLI_CONFIG_DIR` → platform default. `--config`/`TOKLI_CONFIG` still name a single file, which wins over the directory. |
| A6 | CF-001 CLI layer, AC-CF-1 "every key" | Must every schema key have its own CLI flag? | See product question P3. |

## 2. Contradictions

| # | Between | Problem | Proposed fix (spec delta after Gate 1) |
|---|---|---|---|
| X1 | Roadmap S0 exit vs PT-005 | "Same doctor output (minus paths) on all three OSes" cannot hold: doctor prints the Python version and OS/arch, which differ across the matrix by design. | Exit: a **normalised** doctor snapshot (without paths, Python version, OS/arch and Tokli build metadata) is identical in all 9 CI jobs. |
| X2 | SPEC 018 fresh-machine scenario "Alternative port" (`TOKLI_PORT=18787`) vs SPEC 017 env scheme (`TOKLI_<SECTION>__<KEY>`) | `TOKLI_PORT` is not a valid key under the scheme, and CF-003 would reject it as unknown. | Use `TOKLI_SERVER__PORT`. Reserved non-key variables are exactly `TOKLI_CONFIG`, `TOKLI_CONFIG_DIR`, `TOKLI_DATA_DIR` and `TOKLI_DEBUG_CONTENT`. |
| X3 | SPEC 018 status (CI portability job in S1) vs the S0 exit (needs CI on 3 OSes) | It is unclear which fresh-machine scenarios run in S0. | S0 runs the scenarios that apply without a server: clean install, temp HOME, different CWD, no developer config, hostile environment (validation part), read-only CWD, offline doctor. S1 adds the rest. |

## 3. Missing behaviour

| # | Gap | Proposed resolution |
|---|---|---|
| M1 | The YAML config file format is unspecified: duplicate keys, YAML 1.1 booleans (`yes`/`no`), empty file. | Duplicate keys are an error (CF-003). Types are strict (no `yes` → `true` coercion, so a string where a bool is expected is an error). An empty file is an empty layer. |
| M2 | The env value syntax for lists and maps (`tokens.model_map`) is unspecified. | Values of list/map keys are JSON. Scalars are parsed by the key's type. Parse errors name the variable (CF-003). |
| M3 | The doctor exit code is unspecified. | 0 if every check passes, 1 otherwise. A one-line cause and fix for each failure (PT-008). |
| M4 | Platform default directories: only data dirs are named (MD-07). | Config: Windows `%APPDATA%\Tokli`, macOS `~/Library/Application Support/Tokli`, Linux `$XDG_CONFIG_HOME/tokli` (default `~/.config/tokli`). Data: Windows `%LOCALAPPDATA%\Tokli`, macOS `~/Library/Application Support/Tokli`, Linux `$XDG_DATA_HOME/tokli` (default `~/.local/share/tokli`). |
| M5 | Tokenizer provisioning (Q7) is undecided. | See P2. |

## 4. Portability concerns

- **The development machine's default Python is 3.14**, which is unsupported (PT-004, MD-18).
  CPython 3.11 is installed, but 3.12 and 3.13 are not. Local work will use a 3.11 virtual
  environment. 3.12/3.13 are covered only by CI. `requires-python = ">=3.11,<3.14"` makes a 3.14
  install fail loudly, as intended.
- The CI matrix does not exist yet: the repository has no remote (P1).
- The CLI must print ASCII-safe output on a cp1252 console (MD-16).
- Tests must not depend on the developer's HOME, CWD or environment (MD-04, MD-05, MD-08). Every
  test gets a temporary HOME and a scrubbed `TOKLI_*` environment.

## 5. Observability requirements for this slice

S0 has no request path, so traces, spans, telemetry and reason codes do not apply yet
(`TOKLI_OBSERVABILITY.md §8` will record them as N/A with this reason). What applies:

- the doctor output shows every value together with its source;
- no credential or `.env` content is ever read or printed (PT-007, MD-08);
- failures produce one line of cause and one line of fix (PT-008).

## 6. Architectural risks

- **Seams (`CLAUDE.md §5`):** S0 has one tokenizer implementation, one config loader and one
  doctor. All stay concrete classes. `TokenCounter` becomes an interface only when a second
  counter exists.
- **ADR-0001 (to be written in S0; no behaviour change, recorded for review):** build and tooling,
  and persistent third-party dependencies:
  - runtime: `pydantic` v2 (config schema, already chosen in ARCH §9), `PyYAML` (config file),
    `tiktoken` (tokenizer);
  - CLI: stdlib `argparse` (no extra dependency);
  - development: `pytest`, `hypothesis`, `ruff`, `mypy`, `import-linter`;
  - build: `hatchling`, `src/` layout (the import root stays `tokli`, and the source layout
    prevents accidental imports from the CWD, MD-04).
- **Import contracts:** `tokli.cli → tokli.app → {tokli.config, tokli.tokens}`, and
  `tokli.config`/`tokli.tokens` import only the stdlib and their dependencies.

## 7. Product questions (for the human)

| # | Question | Recommendation |
|---|---|---|
| **P1** | **Where does CI run?** The S0 exit needs Windows, Linux and macOS. The repo has no remote. The `gh` CLI is logged in as `PaoloMassignan`. | Create a **private** GitHub repository `PaoloMassignan/tokli`, push, and use GitHub Actions. To save minutes (private repos: macOS minutes count 10×, Windows 2×), run the full 9-job matrix on pull requests to `main`, nightly and on demand. On every other push, run 5 jobs: Linux × 3.11/3.12/3.13, Windows 3.11, macOS 3.13. |
| **P2** | **How is tokenizer data provisioned (Q7)?** The redistribution terms of the BPE data files are not documented, although the `tiktoken` library itself is MIT-licensed. | Do not bundle. `tokli setup tokenizers` downloads only the files the config needs, from the official public location, verifies a SHA-256 pinned in Tokli's code, and stores them in `<data>/tokenizers/`. `--from-file PATH` covers offline machines. CI runs setup once and caches the result. Revisit bundling if the licence becomes clear. |
| **P3** | **CLI surface for configuration (layer 4).** | A generic repeatable `--set section.key=value` on every command, plus named flags only where the specs name them (`--config`, `--config-dir`, `--data-dir`; later `--port`, `--policy`). AC-CF-1 is then satisfied through `--set` for every key. |
| **P4** | **Exit criterion wording (X1).** | Accept the normalised-snapshot wording. |
| **P5** | **Scope readings A1–A6 and X2, X3.** | Accept as proposed. |
| **P6** | **Project licence metadata** for `pyproject.toml`. | None declared for now (private project). Decide before any publication. |

## 8. Implementation decisions (decided by Claude, recorded here)

- Local virtual environment with CPython 3.11 (`py -3.11 -m venv .venv`). `.venv/` is git-ignored.
- `config_hash` = SHA-256 over canonical JSON (sorted keys, `separators=(",", ":")`, UTF-8,
  `ensure_ascii=False`) of the behaviour sections that exist. In S0 that is `tokens`.
- Reserved environment variables as in X2. Any other `TOKLI_*` variable must map to a schema key,
  or it is rejected (AC-CF-2).
- The version string comes from package metadata. There is no hand-maintained constant.
- Tests follow `TOKLI_TEST_STRATEGY.md §2` folders: `tests/unit`, `tests/contract`,
  `tests/integration`.

## 9. Test plan (requirement → tests)

| Requirement / AC | Tests |
|---|---|
| CF-001 (layers 1–4), AC-CF-1 | `test_env_overrides_file_for_every_key`, `test_cli_overrides_env` |
| CF-002 | `test_config_show_reports_sources` |
| CF-003, AC-CF-2 | `test_unknown_key_rejected_with_layer`, `test_duplicate_yaml_key_rejected`, `test_env_json_value_errors_name_variable` |
| CF-004, AC-CF-3, MD-08 | `test_cwd_config_and_dotenv_ignored`, `test_no_dotenv_loading` |
| CF-005 | `test_config_snapshot_immutable` |
| CF-006, AC-CF-4 | `test_config_hash_stable_and_sensitive` |
| CF-008, MD-07 | `test_data_dir_resolution_per_platform`, `test_config_dir_resolution_per_platform` |
| TM-006, AC-TM-2 | `test_missing_tokenizer_fails_with_actionable_message` |
| TM-007, AC-TM-3, MD-20 | `test_import_has_no_side_effects` |
| PT-003 | `test_setup_tokenizers_verifies_sha256`, `test_setup_tokenizers_from_file`, `test_doctor_makes_no_network_calls` |
| PT-004, MD-18 | CI matrix, `test_doctor_reports_python_version` |
| PT-005 (subset), AC-PT-2 | `test_doctor_report_fields`, `test_doctor_normalised_snapshot` |
| PT-007 | `test_doctor_never_prints_secrets` |
| PT-008 (S0 cases), AC-PT-4 | `test_unwritable_data_dir_fails_clearly`, `test_invalid_config_fails_clearly`, `test_missing_tokenizer_fails_with_actionable_message` |
| PT-010, MD-27 | `test_fixtures_contain_no_developer_paths` |
| MD-04, PT-002 | `test_behaviour_independent_of_cwd`, `test_temp_home_clean_start`, `test_hostile_environment_ignored` |
| MD-16 | `test_cli_output_encodable_cp1252` |
| MD-19 | `test_wheel_imports_tokli_in_clean_venv` |
| ARCH §5 | `test_import_contracts` |
| Exit (X1) | CI job comparing `test_doctor_normalised_snapshot` output across the matrix |

New test names (`test_duplicate_yaml_key_rejected`, `test_env_json_value_errors_name_variable`,
`test_config_dir_resolution_per_platform`, `test_setup_tokenizers_*`, `test_doctor_makes_no_network_calls`,
`test_invalid_config_fails_clearly`, `test_doctor_normalised_snapshot`) are added to the specs and
traceability after Gate 1.

## Gate 1 record

Answers (2026-09-29), product owner: "Rendiamo il progetto pubblico su GitHub." · "Confermo tutte e tre. E
accetto le tue proposte rimanenti."

| Question | Decision |
|---|---|
| P1 CI | **Public** GitHub repository `PaoloMassignan/tokli` with GitHub Actions. Public repositories have no minute limits, so the full 9-job matrix runs on every push and pull request. |
| P2 Tokenizer | `tokli setup tokenizers`, pinned SHA-256, `--from-file`, never bundled (TM-010) |
| P3 CLI | Generic `--set section.key=value` plus the named flags (SPEC 017 precedence, layer 4) |
| P4 Exit | Normalised doctor snapshot identical in all 9 jobs (AC-PT-7) |
| P5 Readings | A1–A6, X2, X3 as proposed (SPEC 017, 018 deltas) |
| P6 Licence | Apache-2.0 (`LICENSE`), copyright Paolo Massignan (`NOTICE`) |
| Publication | Single clean initial commit; earlier local history is not published |

Spec delta: SPEC 008 (TM-006 wording, TM-010, Q7 resolved), SPEC 017 (precedence detail, file
format, platform dirs, reserved variables, CF-011, CF-012, AC-CF-6…8), SPEC 018 (PT-012, AC-PT-7,
`TOKLI_SERVER__PORT`, MD-02 control), `TOKLI_ROADMAP.md` S0, traceability rows.

Slice approval: **approved 2026-09-29**, product owner: "Approvo s0".
