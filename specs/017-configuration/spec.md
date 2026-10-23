# SPEC 017 — Configuration

Status: **Approved for S0 (2026-09-29)**: CF-001 (layers 1–4), CF-002 (CLI part), CF-003…CF-006, CF-008, CF-011, CF-012. Other requirements: Draft. · Slice: S0 (loader), S4 (UI overrides)
Approved for S1 (2026-09-30): the keys in "Keys added in S1" and N-level key paths.
Approved for S2 (2026-10-02): the keys in "Keys added in S2".
Changed by S4 SCR-002 (2026-10-03): CF-006 includes the `pruning` section.
Approved for S4 (2026-10-03): CF-001 layer 5 (UI overrides), CF-002 (`ui` source), CF-009, the keys in "Keys added in S4".
Changed by S8a SCR-001 (approved for S8a-1, 2026-10-03): CF-009 (the verbatim opt-in is UI-editable). Approved for S8a-1: the keys in "Keys added in S8a-1".
Approved for S8j (2026-10-22): the keys in "Keys added in S8j".
Changed by S8i SCR-001 (approved for S8i 2026-10-16): "Keys changed in S8i", new CF-013, "Renamed keys", AC-CF-9.
Approved for S8l (2026-10-23): the keys in "Keys added in S8l".
Changed by S8l SCR-001 (approved for S8l 2026-10-23): CF-009 (the keepalive toggles are UI-editable).
Changed by S8l SCR-004 (approved 2026-10-23): the defaults of `keepalive.enabled` and `keepalive.oauth`.

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
3. Environment variables `TOKLI_<SECTION>__<KEY>` (double underscore = nesting), e.g. `TOKLI_COMPRESSION__MIN_SEGMENT_TOKENS=32`.
   Values of list and map keys are JSON; scalars are parsed by the key's type.
4. CLI flags: the generic, repeatable `--set section.key=value` on every command (value syntax as for
   environment variables), plus named flags only where a spec names them (e.g. `--port`).
5. UI overrides (`<data>/ui-overrides.yaml`). Only for keys marked `ui_editable` **and** not set by layers 3–4: a UI value replaces layers 1–2, never layers 3–4. A key set by env or CLI is reported as locked, with its source (API-005).

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
| `compression.verbatim_tools` | `["Read", "Bash", "PowerShell", "shell", "shell_command", "container.exec"]` (`PowerShell` since S8h SCR-002) |
| `compression.min_segment_tokens` | `64` |
| `compression.min_gain_tokens` / `min_gain_ratio` | `4` / `0.01` |
| `compression.request_budget_ms` / `per_call_timeout_ms` | `50` / `200` |
| `compression.verify_lossless` | `false` |
| `compressors.json_minify.enabled` | `true` (provisional, QE-016) |
| `observability.trace_buffer` / `response_header` | `500` / `true` |
| `observability.log_format` (also `--log-format`) | `json` (or `text`) |
| `telemetry.retention_days` | `30` |

## Keys added in S2

| Key | Default |
|---|---|
| `limits.usage_parser_buffer` | `1048576` (AN-009) |
| `compression.result_cache_mb` | `64`; `0` disables the cache (CC-024) |
| `observability.log_file` | `false` (OB-013) |

## Keys added in S4

| Key | Default |
|---|---|
| `pruning.duplicate_min_tokens` | `64` (SPEC 019, POLICY provisional) |
| `pruning.duplicate_require_same_call` | `false` (SPEC 019) |
| `compressors.duplicate_tool_results.enabled` | `true` (E11 smoke record `no_measurable_damage`, 2026-10-03; CC-020) |

UI-editable (CF-009): `compressors.<id>.enabled`, `telemetry.retention_days`.

## Keys added in S8e (approved for S8e, 2026-10-04)

| Key | Default |
|---|---|
| `compressors.reread_by_reference.enabled` | `true` (version 2 smoke record `no_measurable_damage` on `claude-opus-5-5`, 2026-10-09, in Claude Code's numbering; S8h SCR-001; CC-020) |
| `pruning.reread_tools` | `["Read"]` |
| `pruning.reread_min_run_lines` | `5` (S8e review P4) |
| `pruning.reread_max_lines` | `20000` (ADR 0013) |

## Keys added in S8c (approved for S8c, 2026-10-04)

| Key | Default |
|---|---|
| `compressors.edit_args_on_resume.enabled` | `false` (SELECTIVE; CC-002) |
| `pruning.resume_after_s` | `3600` (S8c review P4; rewrites follow pauses of more than an hour, E5b-lite). Renamed in S8i (CF-013). |
| `pruning.resume_min_age_turns` | `4` |
| `pruning.resume_min_tokens` | `64` (per argument string) |
| `pruning.resume_edit_fields` | `{"Write": ["content"], "Edit": ["old_string", "new_string"], "MultiEdit": ["edits/*/old_string", "edits/*/new_string"]}` |
| `pruning.conversation_states` | `1024` (ADR 0012) |

## Keys added in S8j

| Key | Default |
|---|---|
| `compressors.outline_first_read.enabled` | `false` (SELECTIVE; CC-002; E10(f): damage detected) |
| `pruning.outline_tools` | `["Read", "Bash", "PowerShell"]` (S8j review P1) |
| `pruning.outline_rules` | `{"py": "python", "cs": "c_family", "java": "c_family", "kt": "c_family", "ts": "c_family", "tsx": "c_family", "js": "c_family", "jsx": "c_family", "go": "c_family", "rs": "c_family", "c": "c_family", "h": "c_family", "cpp": "c_family", "hpp": "c_family"}` (code only, S8j review C; values ∈ `python`, `c_family`) |
| `pruning.outline_min_tokens` | `500` (S8j review P5) |
| `pruning.outline_min_run_lines` | `3` (S8j review P4) |

## Keys changed in S8i (S8i SCR-001)

| Key | Default |
|---|---|
| `pruning.cache_ttl_default_s` | `{anthropic_messages: 3600}`: the cache lifetime, per protocol, when the request states none that Tokli understands (SPEC 019 PR-027; S8i review P2). One entry per protocol with an adapter. |
| `pruning.resume_margin_s` | `60` (SPEC 019 PR-021; S8i review P3) |
| `pruning.resume_after_s` | removed; renamed to `pruning.cache_ttl_default_s.anthropic_messages` (CF-013) |

## Renamed keys

| Old key | New key | Since |
|---|---|---|
| `pruning.resume_after_s` | `pruning.cache_ttl_default_s.anthropic_messages` | S8i |

## Keys added in S8l

The `keepalive` section does not change forwarded bodies and is not part of `config_hash` (CF-006).

| Key | Default |
|---|---|
| `keepalive.enabled` | `true` (SPEC 020 KA-001; S8l SCR-004; UI-editable) |
| `keepalive.oauth` | `true` (S8l SCR-004; UI-editable) |
| `keepalive.horizon_s` | `43200` (12 h, the best net in the S8l simulation; S8l review P4) |
| `keepalive.lead_s` | `300` (a ping 5 min before the lifetime ends; S8l review P4) |
| `keepalive.min_ttl_s` | `3600` (one-hour lifetimes only; SPEC 020 rationale) |
| `keepalive.min_prefix_tokens` | `20000` (provider tokens; S8l review P4) |
| `keepalive.max_conversations` | `8` (S8l review P4) |

## Keys added in S8a-1

| Key | Default |
|---|---|
| `compressors.search_group.enabled` | `false` (no evaluation record; CC-020) |
| `compressors.search_group.min_group_lines` | `5` (SPEC 010) |
| `compressors.search_group.apply_to_verbatim_tools` | `false` (CC-021, S8a SCR-001; UI-editable) |
| `compressors.log_filter.enabled` | `false` (SELECTIVE, never on by default; CC-002) |
| `compressors.log_filter.debug_sample` | `10` (SPEC 010) |
| `compressors.log_filter.apply_to_verbatim_tools` | `false` (CC-021, S8a SCR-001; UI-editable) |

## Requirements

| ID | EARS requirement |
|---|---|
| CF-001 | THE SYSTEM SHALL resolve every setting by the precedence above, uniformly for every key. |
| CF-002 | THE SYSTEM SHALL expose the effective configuration with each key's source (`default`, `file:<path>`, `env:<VAR>`, `cli:<flag>`, `ui`) via `tokli config show` and the API. |
| CF-003 | IF any layer contains an unknown key, a wrong type or an out-of-range value, THEN THE SYSTEM SHALL refuse to start (or reject the PATCH) with an error naming the layer, key and expected type. |
| CF-004 | THE SYSTEM SHALL NOT read configuration or `.env` files from the current working directory unless the path is given explicitly. |
| CF-005 | THE effective configuration SHALL be an immutable snapshot. Changes produce a new snapshot applied to subsequent requests only. |
| CF-006 | THE SYSTEM SHALL compute `config_hash` over the canonical JSON of behaviour-affecting keys (sections `compression`, `compressors`, `pipeline`, `pruning`, `tokens`, `limits`, where present), excluding paths, ports and credentials. |
| CF-007 | WHEN a configured optional capability cannot be provided (missing dependency or file), THE SYSTEM SHALL either fail at startup (if marked `required`) or report it as unavailable, and SHALL NOT substitute a different behaviour silently. |
| CF-008 | THE SYSTEM SHALL resolve the data dir as `--data-dir` → `TOKLI_DATA_DIR` → platform default, and the config dir as `--config-dir` → `TOKLI_CONFIG_DIR` → platform default (table above), and SHALL print both at startup and in `tokli doctor`. |
| CF-009 | THE configuration schema SHALL mark each key as `ui_editable` or not. v1 UI-editable keys: `compressors.<id>.enabled`, `compressors.<id>.apply_to_verbatim_tools` (where it exists), `telemetry.retention_days`, `keepalive.enabled`, `keepalive.oauth`. (S4 SCR-001: there is no policy key. S8a SCR-001: the verbatim opt-in. S8l SCR-001: the keepalive toggles.) |
| CF-010 | Secrets SHALL NOT be configurable by value in the config file. Only references (`key_env`, `key_file`) are allowed. |
| CF-011 | WHEN an environment variable starting with `TOKLI_` is neither a reserved variable nor the name of a schema key, or its value does not parse for the key's type, THE SYSTEM SHALL refuse to start with an error naming the variable. |
| CF-012 | THE config file reader SHALL reject duplicate keys and values whose YAML type does not match the schema type, naming the file, key and expected type. |
| CF-013 | WHEN a layer sets a key listed in "Renamed keys", THE SYSTEM SHALL use its value for the new key, SHALL print a warning naming the layer, the old key and the new key at startup and in `tokli doctor`, and SHALL refuse to start (CF-003) if the same layer also sets the new key. (S8i SCR-001.) |

## Acceptance criteria
- AC-CF-1: parametrised test over every schema key: file < env < CLI resolves as specified, and the source is reported. For UI-editable keys: file < UI, and env/CLI always win over UI (the key is reported locked).
- AC-CF-2: an unknown key in the file → startup error naming it. The same for env `TOKLI_COMPRESION__MIN_SEGMENT_TOKENS` (typo).
- AC-CF-3: a `tokli.yaml` and `.env` placed in CWD are ignored (test runs from that CWD).
- AC-CF-4: `config_hash` is stable across OSes and changes when any behaviour key changes.
- AC-CF-5: a config file containing `api_key: sk-…` → startup error "secrets must be referenced via key_env/key_file".
- AC-CF-6 (CF-011): `TOKLI_TOKENS__MODEL_MAP='[not json'` → error naming the variable. `TOKLI_FOO=1` → error naming it. `TOKLI_DATA_DIR` is accepted.
- AC-CF-7 (CF-012): a file with a duplicated key, and a file with `yes` for a boolean key, are each rejected with file, key and expected type.
- AC-CF-9 (CF-013): `pruning.resume_after_s: 120` in the file → `cache_ttl_default_s.anthropic_messages = 120` with source `file:<path>` and a warning naming both keys; the same through `TOKLI_PRUNING__RESUME_AFTER_S` and `--set`. Both keys in one layer → startup error naming the layer and both keys.
- AC-CF-8 (CF-008): config and data dirs resolve per the table on each OS (platform mocked), and flags and variables override them.

## Test scenarios
`test_env_overrides_file_for_every_key` · `test_cli_overrides_env` · `test_ui_override_only_when_not_pinned` ·
`test_config_show_reports_sources` · `test_unknown_key_rejected_with_layer` · `test_cwd_config_and_dotenv_ignored` ·
`test_config_snapshot_immutable` · `test_config_hash_stable_and_sensitive` · `test_optional_capability_never_silently_substituted` ·
`test_data_dir_resolution_per_platform` · `test_secret_values_rejected_in_config` ·
`test_config_dir_resolution_per_platform` · `test_env_json_value_errors_name_variable` · `test_reserved_env_vars_only` ·
`test_duplicate_yaml_key_rejected` · `test_yaml_implicit_types_rejected` · `test_set_flag_overrides_env` ·
`test_renamed_key_resume_after_s`
