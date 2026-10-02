# SPEC 018 — Portability, reproducibility and diagnostics

Status: **Approved for S0 (2026-09-29)**: PT-003 (setup command), PT-004, PT-005 (S0 subset), PT-007, PT-008 (invalid config, unwritable data dir, missing tokenizer), PT-010, PT-011 (MD-02, MD-04, MD-05, MD-07, MD-08, MD-16, MD-18, MD-19, MD-20, MD-27), PT-012. Other requirements: Draft. · Slices: S0 (doctor basic, server-less fresh-machine scenarios), S1 (remaining scenarios), S9 (fingerprint + UI)
Approved for S1 (2026-09-30): PT-008 (port in use), fresh-machine scenarios for `serve`, MD-09, MD-10, MD-12, MD-22, MD-23, MD-24, MD-25.
Related: SPEC 017 (configuration), TOKLI_TEST_STRATEGY.md §2

## Purpose
Make machine-specific behaviour impossible to hide, and make differences between two
installations explainable in one command.

## Requirements

| ID | EARS requirement |
|---|---|
| PT-001 | Tokli SHALL behave equivalently on two clean supported machines given the same explicit configuration and inputs. Any environment-dependent difference SHALL either be intentionally specified or reported diagnostically. |
| PT-002 | WHEN Tokli starts on a supported clean machine with valid explicit configuration, THE SYSTEM SHALL NOT depend on state from a developer workstation (no CWD files, no inherited provider env vars unless configured, no pre-existing caches beyond the provisioned tokenizer). |
| PT-003 | THE SYSTEM SHALL make outbound network connections only to configured upstreams (runtime), and to tokenizer sources only during the explicit `tokli setup tokenizers` command. |
| PT-004 | THE supported platform set SHALL be exactly the CI matrix: Windows, Linux, macOS × CPython 3.11, 3.12, 3.13. `requires-python` SHALL match. |
| PT-005 | `tokli doctor` SHALL report: Tokli version, Python, OS/arch, config and data paths, effective config with sources (secrets masked as present/absent), listen address and port, upstream URLs, auth mode and credential-source presence per provider, registry with availability, tokenizer id + data hash, telemetry DB path/schema/size, debug-content state, degraded checks, and warnings. |
| PT-006 | `tokli doctor --fingerprint` SHALL print a behavioural fingerprint (config hash, registry versions, tokenizer hash, golden-corpus output hash). `--explain` SHALL name the differing component and the first differing corpus case when compared with `--against <fingerprint.json>`. |
| PT-007 | THE doctor SHALL never print credential values, prompt content or file contents. |
| PT-008 | WHEN any port-in-use, unwritable-data-dir, missing-tokenizer or invalid-config condition occurs at startup, THE SYSTEM SHALL exit non-zero with a one-line cause and a one-line fix. |
| PT-009 | THE SYSTEM SHALL behave identically for LF, CRLF and mixed line endings in the sense declared by each compressor's spec (tested per compressor). |
| PT-010 | THE test fixtures SHALL contain no developer-specific absolute paths, usernames or hostnames. |
| PT-012 | `tokli doctor` SHALL exit 0 when every check passes and 1 otherwise, printing for each failed check one line of cause and one line of fix. In S0 it SHALL report: Tokli version, Python, OS/arch, config dir, config file, data dir, the effective configuration with each key's source, and each configured tokenizer's id, file hash and status. Each later slice adds the PT-005 fields it introduces. |
| PT-011 | THE SYSTEM SHALL implement the control of every machine-dependence hazard in the checklist below, and each control SHALL be verified by the listed test. |

## Acceptance criteria
- AC-PT-1: the CI portability job runs the fresh-machine scenarios below on all 3 OSes, and the fingerprints are equal to the committed value.
- AC-PT-6 (PT-011): every checklist row with a test has that test in the suite (a contract test reads the table's test names).
- AC-PT-2: doctor output snapshot test (paths normalised), plus a canary scan for secrets.
- AC-PT-7 (PT-012): the **normalised** doctor snapshot (without paths, Python version, OS/arch and build metadata) is byte-identical in every CI job of the matrix. Doctor makes no network connection.
- AC-PT-3: a socket guard in integration tests fails on any non-loopback connection other than the fake upstream.
- AC-PT-4: each startup failure case in PT-008 has a test asserting exit code and message.
- AC-PT-5: `--explain` pinpoints an injected difference (a toggled compressor; a different tokenizer file).

## Test scenarios
`test_fingerprint_equal_across_os` (CI) · `test_behaviour_independent_of_cwd` · `test_temp_home_clean_start` ·
`test_hostile_environment_ignored` · `test_no_outbound_connections_except_upstream` ·
`test_doctor_report_fields` · `test_doctor_reports_python_version` · `test_doctor_never_prints_secrets` ·
`test_fingerprint_explain_config_difference` · `test_fingerprint_explain_tokenizer_difference` ·
`test_port_in_use_fails_clearly` · `test_unwritable_data_dir_fails_clearly` ·
`test_missing_tokenizer_fails_with_actionable_message` · `test_fixtures_contain_no_developer_paths` ·
`test_alternative_port` ·
`test_no_dotenv_loading` · `test_cli_output_encodable_cp1252` · `test_daily_rollup_respects_tz_param` ·
`test_wheel_imports_tokli_in_clean_venv` · `test_no_module_reads_cwd_relative_paths` ·
`test_doctor_normalised_snapshot` · `test_doctor_makes_no_network_calls` · `test_invalid_config_fails_clearly`

## Machine-dependence checklist

Each row is a way a local proxy's behaviour can silently depend on the machine instead of on
explicit configuration. Risk: **H** can change what is forwarded or whether requests work; **M**
changes metrics or diagnostics, or fails loudly; **L** is cosmetic or rare.

| Id | Hazard | Risk | Tokli control | Verification |
|---|---|---|---|---|
| MD-01 | Optional model files (e.g. a learned router) looked up next to the code or in the working directory, and used only if present | H | No learned routing in v1. Any future model is a declared dependency with an explicit configured path. If it is absent, the component is `unavailable`, never replaced silently. | `test_no_module_reads_cwd_relative_paths`; fingerprint |
| MD-02 | Tokenizer data downloaded on first use, loaded at import time | H | Tokenizer data provisioned explicitly by `tokli setup tokenizers` into `<data>/tokenizers/`, with a pinned SHA-256 check (TM-010). Never bundled. Loaded at bootstrap, never at import. Missing → startup error naming the path and the fix. | `test_starts_offline_with_provisioned_tokenizer`, `test_missing_tokenizer_fails_with_actionable_message` |
| MD-03 | Optional parser libraries missing → the compressor silently returns its input | M | `requires=(…)` → `unavailable(dep)` in API, UI and doctor | `test_missing_dependency_marks_compressor_unavailable` |
| MD-04 | Config and state relative to the launch directory | H | No workspace concept. Config: `--config` → `TOKLI_CONFIG` → platform config dir. Data: `--data-dir` → `TOKLI_DATA_DIR` → platform data dir. Never CWD. Both printed at startup and by doctor. | `test_behaviour_independent_of_cwd` |
| MD-05 | Environment overrides honoured only when no config file exists | H | One precedence chain for every key (SPEC 017) | `test_env_overrides_file_for_every_key` |
| MD-06 | Credentials discovered from many locations or inherited environment variables | H | Passthrough by default. Inject mode needs exactly one configured source per provider (`key_env` or `key_file`). No search path. | `test_inject_uses_only_configured_source`, `test_inherited_provider_env_is_ignored_unless_configured` |
| MD-07 | Hard-coded install directories | M | Platform dirs (Windows `%LOCALAPPDATA%\Tokli`, macOS `~/Library/Application Support/Tokli`, Linux `$XDG_DATA_HOME/tokli`), always overridable and printed | `test_data_dir_resolution_per_platform` |
| MD-08 | Automatic `.env` loading from the working directory | H | No dotenv loading | `test_no_dotenv_loading` (static scan) |
| MD-09 | Fixed ports, wildcard bind address | M | Default `127.0.0.1:8787`. A non-loopback bind requires `--allow-remote` and warns. Port conflict → clear error, no auto-increment. | `test_default_bind_is_loopback`, `test_port_in_use_fails_clearly`, `test_alternative_port` |
| MD-10 | Unknown paths defaulted to one provider | M | Provider only from an explicit path prefix | `test_unknown_prefix_returns_tokli_404` |
| MD-11 | Windows absolute paths in tool output (`C:\…:12:`) | H | Compressor specs cover drive-letter and UNC paths. Compat fixtures include Windows and POSIX variants. | `test_search_group_windows_paths_roundtrip` |
| MD-12 | CRLF line endings in tool output | M | Every text compressor states its CRLF behaviour. Byte-lossless decoders are tested with CRLF, LF and mixed input. | `test_<compressor>_crlf_roundtrip` |
| MD-13 | Client traffic differs per OS (e.g. Codex PowerShell strings vs argv) | M | Adapters resolve `tool_name` generically. Tool semantics are config. The compat corpus has both shapes. | compat fixtures `responses_codex_windows.json`, `responses_codex_unix.json` |
| MD-14 | Key-file encodings (BOM, UTF-16, invisible characters) | M | UP-007 normalisation. Doctor reports "present, BOM stripped" or the encoding problem. | `test_key_file_with_bom_is_accepted`, `test_utf16_key_file_reported` |
| MD-15 | Permission bits have no effect on Windows | L | No credentials stored by default. The data dir holds nothing secret. | doctor check (informational) |
| MD-16 | Console encoding (e.g. cp1252) | L | CLI output is ASCII-safe or written with `errors="replace"`. Log files are UTF-8. | `test_cli_output_encodable_cp1252` |
| MD-17 | Time zones | L | UTC with offset stored. The API groups by a `tz` parameter. | `test_daily_rollup_respects_tz_param` |
| MD-18 | Python version drift between machines and CI | M | `requires-python` equals the CI matrix (PT-004). Doctor prints the interpreter. | CI matrix, `test_doctor_reports_python_version` |
| MD-19 | Generic top-level package names that collide with other projects | M | Import root `tokli` | `test_wheel_imports_tokli_in_clean_venv` |
| MD-20 | Import-time environment checks | M | No import-time side effects. Config is read only in `bootstrap()`. | `test_import_has_no_side_effects` |
| MD-21 | UI assets that require a build step | M | Static assets shipped in the wheel | `test_wheel_contains_ui_assets` |
| MD-22 | Prompt content in working-directory logs | H | No content persisted by default (OB-008) | `test_default_logging_contains_no_prompt_text` |
| MD-23 | Unbounded in-memory state | M | SQLite with retention. Bounded trace ring buffer. | `test_trace_buffer_bounded`, `test_retention_pruning` |
| MD-24 | Network access besides the upstreams | H | Only configured upstreams (PT-003) | `test_no_outbound_connections_except_upstream` |
| MD-25 | Silent identity on errors | M | The engine records `failed` with a reason | `test_compressor_exception_is_recorded` |
| MD-26 | Container vs native differences | L | Containers are not a v1 deliverable. If added, same precedence, and doctor states `runtime: container`. | — |
| MD-27 | Developer paths and usernames in fixtures | L | Fixture lint. Windows-path fixtures use a neutral user (`C:\Users\dev\…`). | `test_fixtures_contain_no_developer_paths` |
| MD-28 | Locale-dependent behaviour | L | Explicit ASCII classes where ASCII is meant. Ordering never depends on locale. | determinism fingerprint across OSes |

## Reproducibility mechanism

**Behavioural fingerprint.** `tokli doctor --fingerprint` prints a hash computed from:

1. the effective compression-relevant configuration (canonical JSON, sources excluded);
2. the registry: compressor ids, versions, kinds, availability;
3. tokenizer id plus the SHA-256 of its data file;
4. the outputs of running the pipeline over the **built-in golden corpus** (`tests/golden`: about 40
   synthetic agent requests covering all three protocols, CRLF/LF, Windows/POSIX paths, JSON,
   grep, diff, logs, reminders, images and thinking blocks): SHA-256 over the rendered bodies and
   per-compressor stats.

Two installs with identical explicit configuration print the same fingerprint. If they do not,
`--explain` names the differing component (config / registry / tokenizer / corpus output) and the
first differing corpus case. CI runs the fingerprint on Windows, Linux and macOS × supported Python
versions, and asserts equality with a committed expected value (updated deliberately when
behaviour changes).

## Fresh-machine scenarios (CI job `portability`)

| Scenario | Setup | Pass condition |
|---|---|---|
| Clean install | new venv, `pip install dist/*.whl` | `tokli doctor` exits 0 (with provisioned tokenizer) |
| Temp HOME | `HOME`/`USERPROFILE`/`LOCALAPPDATA`/`XDG_*` → empty temp dirs | same fingerprint; data dir created under temp |
| Different CWD | run from two unrelated temp dirs | same fingerprint; no files created in CWD |
| No developer config | no config file anywhere | defaults applied; doctor lists every key with source `default` |
| Alternative port | `--port 0` (ephemeral) and `TOKLI_SERVER__PORT=18787` | serve works; doctor/health report the actual port |
| Offline | outbound network blocked except a local fake upstream | serve + proxy fixtures pass |
| Missing optional dependency | uninstall an optional extra (when one exists) | compressor reported `unavailable(dep)`; the fingerprint component "registry" differs and `--explain` says why |
| Hostile environment | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TOKLI_*` junk values set | passthrough mode unaffected; config validation errors name the variable |
| Read-only CWD | CWD not writable | serve works |
