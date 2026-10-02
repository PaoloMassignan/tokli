# SPEC 017 — Configuration

Status: **Approved for S0 (2026-09-29)**: CF-001 (layers 1–4), CF-002 (CLI part), CF-003…CF-006, CF-008, CF-011, CF-012. Other requirements: Draft. · Slice: S0 (loader), S4 (UI overrides)
Approved for S1 (2026-09-30): the keys in "Keys added in S1" and N-level key paths.

## Purpose
Every behaviour-affecting setting has one definition, one precedence rule and a visible source.

## Rationale
- Environment variables are honoured uniformly, whether or not a config file exists.
- Nothing is read from the current working directory implicitly.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 017 rows).

## Precedence (lowest → highest)

1. Built-in defaults (in the schema).
2. Config file: `--config PATH` → `TOKLI_CONFIG` → `<config dir>/tokli.yaml` (if present), where the config dir is
   `--config-dir` → `TOKLI_CONFIG_DIR` → platform default. **Never CWD.**
3. Environment variables `TOKLI_<SECTION>__<KEY>` (double underscore = nesting), e.g. `TOKLI_COMPRESSION__POLICY=LOSSY_ALLOWED`.
   Values of list and map keys are JSON; scalars are parsed by the key's type.
4. CLI flags: the generic, repeatable `--set section.key=value` on every command (value syntax as for
   environment variables), plus named flags only where a spec names them (e.g. `--port`, `--policy`).
5. UI overrides (`<data>/ui-overrides.yaml`). Only for keys marked `ui_editable` **and** not pinned by layers 3–4.

Rationale for UI above file but below env/CLI: operators who pin behaviour (CI, scripts) must not
be surprised by a UI click, and UI users still see their changes take effect over the file
defaults.

## File format and platform directories

- The config file is YAML, read strictly: duplicate keys are an error, and no implicit type
  coercion is applied (for example `yes` is not a boolean for a boolean key; it is a type error).
  An empty file is an empty layer.
- Platform default directories:

| OS | Config dir | Data dir |
|---|---|---|
| Windows | `%APPDATA%\Tokli` | `%LOCALAPPDATA%\Tokli` |
| macOS | `~/Library/Application Support/Tokli` | `~/Library/Application Support/Tokli` |
| Linux | `$XDG_CONFIG_HOME/tokli` (default `~/.config/tokli`) | `$XDG_DATA_HOME/tokli` (default `~/.local/share/tokli`) |

- Keys may be nested to any depth (for example `compressors.json_minify.enabled`). Environment
  variables use `__` for each level: `TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED`.
- Reserved environment variables that are **not** schema keys: `TOKLI_CONFIG`, `TOKLI_CONFIG_DIR`,
  `TOKLI_DATA_DIR`, `TOKLI_DEBUG_CONTENT`.

## Keys added in S1

| Key | Default |
|---|---|
| `server.host` / `server.port` | `127.0.0.1` / `8787` |
| `server.allow_remote` (also `--allow-remote`) | `false` |
| `upstreams.anthropic.base_url` | `https://api.anthropic.com` |
| `upstreams.anthropic.connect_timeout_s` / `read_timeout_s` | `10` / `600` |
| `tls.ca_bundle` | `null` |
| `limits.max_transform_bytes` | `33554432` |
| `compression.segment_kinds` | `["TOOL_RESULT", "USER_TEXT"]` |
| `compression.verbatim_tools` | `["Read", "Bash", "shell", "shell_command", "container.exec"]` |
| `compression.min_segment_tokens` | `64` |
| `compression.min_gain_tokens` / `min_gain_ratio` | `4` / `0.01` |
| `compression.request_budget_ms` / `per_call_timeout_ms` | `50` / `200` |
| `compression.verify_lossless` | `false` |
| `compressors.json_minify.enabled` | `true` (provisional, QE-016) |
| `observability.trace_buffer` / `response_header` | `500` / `true` |
| `observability.log_format` (also `--log-format`) | `json` (or `text`) |
| `telemetry.retention_days` | `30` |

## Requirements

| ID | EARS requirement |
|---|---|
| CF-001 | THE SYSTEM SHALL resolve every setting by the precedence above, uniformly for every key. |
| CF-002 | THE SYSTEM SHALL expose the effective configuration with each key's source (`default`, `file:<path>`, `env:<VAR>`, `cli:<flag>`, `ui`) via `tokli config show` and the API. |
| CF-003 | IF any layer contains an unknown key, a wrong type or an out-of-range value, THEN THE SYSTEM SHALL refuse to start (or reject the PATCH) with an error naming the layer, key and expected type. |
| CF-004 | THE SYSTEM SHALL NOT read configuration or `.env` files from the current working directory unless the path is given explicitly. |
| CF-005 | THE effective configuration SHALL be an immutable snapshot. Changes produce a new snapshot applied to subsequent requests only. |
| CF-006 | THE SYSTEM SHALL compute `config_hash` over the canonical JSON of behaviour-affecting keys (sections `compression`, `compressors`, `pipeline`, `tokens`, `limits`, where present), excluding paths, ports and credentials. |
| CF-007 | WHEN a configured optional capability cannot be provided (missing dependency or file), THE SYSTEM SHALL either fail at startup (if marked `required`) or report it as unavailable, and SHALL NOT substitute a different behaviour silently. |
| CF-008 | THE SYSTEM SHALL resolve the data dir as `--data-dir` → `TOKLI_DATA_DIR` → platform default, and the config dir as `--config-dir` → `TOKLI_CONFIG_DIR` → platform default (table above), and SHALL print both at startup and in `tokli doctor`. |
| CF-009 | THE configuration schema SHALL mark each key as `ui_editable` or not. v1 UI-editable keys: `compression.policy`, `compressors.<id>.enabled`, `telemetry.retention_days`. |
| CF-010 | Secrets SHALL NOT be configurable by value in the config file. Only references (`key_env`, `key_file`) are allowed. |
| CF-011 | WHEN an environment variable starting with `TOKLI_` is neither a reserved variable nor the name of a schema key, or its value does not parse for the key's type, THE SYSTEM SHALL refuse to start with an error naming the variable. |
| CF-012 | THE config file reader SHALL reject duplicate keys and values whose YAML type does not match the schema type, naming the file, key and expected type. |

## Acceptance criteria
- AC-CF-1: parametrised test over every schema key: file < env < CLI < UI (when editable) resolves as specified, and the source is reported.
- AC-CF-2: an unknown key in the file → startup error naming it. The same for env `TOKLI_COMPRESION__POLICY` (typo).
- AC-CF-3: a `tokli.yaml` and `.env` placed in CWD are ignored (test runs from that CWD).
- AC-CF-4: `config_hash` is stable across OSes and changes when any behaviour key changes.
- AC-CF-5: a config file containing `api_key: sk-…` → startup error "secrets must be referenced via key_env/key_file".
- AC-CF-6 (CF-011): `TOKLI_TOKENS__MODEL_MAP='[not json'` → error naming the variable. `TOKLI_FOO=1` → error naming it. `TOKLI_DATA_DIR` is accepted.
- AC-CF-7 (CF-012): a file with a duplicated key, and a file with `yes` for a boolean key, are each rejected with file, key and expected type.
- AC-CF-8 (CF-008): config and data dirs resolve per the table on each OS (platform mocked), and flags and variables override them.

## Test scenarios
`test_env_overrides_file_for_every_key` · `test_cli_overrides_env` · `test_ui_override_only_when_not_pinned` ·
`test_config_show_reports_sources` · `test_unknown_key_rejected_with_layer` · `test_cwd_config_and_dotenv_ignored` ·
`test_config_snapshot_immutable` · `test_config_hash_stable_and_sensitive` · `test_optional_capability_never_silently_substituted` ·
`test_data_dir_resolution_per_platform` · `test_secret_values_rejected_in_config` ·
`test_config_dir_resolution_per_platform` · `test_env_json_value_errors_name_variable` · `test_reserved_env_vars_only` ·
`test_duplicate_yaml_key_rejected` · `test_yaml_implicit_types_rejected` · `test_set_flag_overrides_env`
