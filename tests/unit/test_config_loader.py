"""SPEC 017: precedence, sources, strict validation, immutability, config hash."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.helpers import platform_name
from tokli.config import CliOverrides, ConfigError, load_config, schema_keys
from tokli.config.yamlfile import load_strict_yaml

# One alternative value per schema key: (YAML text for the file layer, env/--set text, expected).
# A new schema key without an entry here fails test_env_overrides_file_for_every_key.
EXAMPLES: dict[str, tuple[str, str, object]] = {
    "server.host": ("localhost", "127.0.0.2", "127.0.0.2"),
    "server.port": ("9000", "9001", 9001),
    "server.allow_remote": ("true", "false", False),
    "upstreams.anthropic.base_url": ("https://a.invalid", "https://b.invalid", "https://b.invalid"),
    "upstreams.anthropic.connect_timeout_s": ("5", "7.5", 7.5),
    "upstreams.anthropic.read_timeout_s": ("100", "200", 200),
    "tls.ca_bundle": ("a.pem", "b.pem", "b.pem"),
    "limits.max_transform_bytes": ("1000", "2000", 2000),
    "limits.usage_parser_buffer": ("4096", "8192", 8192),
    "compression.result_cache_mb": ("0", "8", 8),
    "compression.segment_kinds": ("[TOOL_RESULT]", '["USER_TEXT"]', ("USER_TEXT",)),
    "compression.verbatim_tools": ("[Read]", '["Bash"]', ("Bash",)),
    "compression.min_segment_tokens": ("10", "20", 20),
    "compression.min_gain_tokens": ("1", "2", 2),
    "compression.min_gain_ratio": ("0.5", "0.25", 0.25),
    "compression.request_budget_ms": ("10", "20", 20),
    "compression.per_call_timeout_ms": ("10", "20", 20),
    "compression.verify_lossless": ("true", "false", False),
    "compressors.json_minify.enabled": ("false", "true", True),
    "compressors.duplicate_tool_results.enabled": ("false", "true", True),
    "compressors.search_group.enabled": ("true", "false", False),
    "compressors.search_group.min_group_lines": ("7", "9", 9),
    "compressors.search_group.apply_to_verbatim_tools": ("true", "false", False),
    "compressors.log_filter.enabled": ("true", "false", False),
    "compressors.log_filter.debug_sample": ("5", "20", 20),
    "compressors.log_filter.apply_to_verbatim_tools": ("true", "false", False),
    "compressors.edit_args_on_resume.enabled": ("true", "false", False),
    "pruning.resume_after_s": ("60", "120", 120.0),
    "pruning.resume_min_age_turns": ("2", "6", 6),
    "pruning.resume_min_tokens": ("10", "20", 20),
    "pruning.resume_edit_fields": (
        "{Write: [content]}",
        '{"Edit": ["old_string"]}',
        {"Edit": ("old_string",)},  # values are frozen (lists become tuples)
    ),
    "pruning.conversation_states": ("8", "16", 16),
    "compressors.reread_by_reference.enabled": ("true", "false", False),
    "pruning.reread_tools": ("[Read, Cat]", '["Read"]', ("Read",)),
    "pruning.reread_min_run_lines": ("3", "7", 7),
    "pruning.reread_max_lines": ("100", "200", 200),
    "pruning.duplicate_min_tokens": ("10", "20", 20),
    "pruning.duplicate_require_same_call": ("true", "false", False),
    "tokens.default": ("cl100k_base", "o200k_base", "o200k_base"),
    "tokens.model_map": (
        '[{pattern: "x-*", tokenizer: cl100k_base}]',
        '[{"pattern": "y-*", "tokenizer": "o200k_base"}]',
        ({"pattern": "y-*", "tokenizer": "o200k_base"},),
    ),
    "observability.trace_buffer": ("10", "20", 20),
    "observability.response_header": ("false", "true", True),
    "observability.log_format": ("text", "json", "json"),
    "observability.log_file": ("true", "false", False),
    "telemetry.retention_days": ("1", "2", 2),
}
FILE_EXPECTED: dict[str, object] = {
    "server.host": "localhost",
    "server.port": 9000,
    "server.allow_remote": True,
    "upstreams.anthropic.base_url": "https://a.invalid",
    "upstreams.anthropic.connect_timeout_s": 5,
    "upstreams.anthropic.read_timeout_s": 100,
    "tls.ca_bundle": "a.pem",
    "limits.max_transform_bytes": 1000,
    "limits.usage_parser_buffer": 4096,
    "compression.result_cache_mb": 0,
    "compression.segment_kinds": ("TOOL_RESULT",),
    "compression.verbatim_tools": ("Read",),
    "compression.min_segment_tokens": 10,
    "compression.min_gain_tokens": 1,
    "compression.min_gain_ratio": 0.5,
    "compression.request_budget_ms": 10,
    "compression.per_call_timeout_ms": 10,
    "compression.verify_lossless": True,
    "compressors.json_minify.enabled": False,
    "compressors.duplicate_tool_results.enabled": False,
    "compressors.search_group.enabled": True,
    "compressors.search_group.min_group_lines": 7,
    "compressors.search_group.apply_to_verbatim_tools": True,
    "compressors.log_filter.enabled": True,
    "compressors.log_filter.debug_sample": 5,
    "compressors.edit_args_on_resume.enabled": True,
    "pruning.resume_after_s": 60.0,
    "pruning.resume_min_age_turns": 2,
    "pruning.resume_min_tokens": 10,
    "pruning.resume_edit_fields": {"Write": ("content",)},
    "pruning.conversation_states": 8,
    "compressors.reread_by_reference.enabled": True,
    "pruning.reread_tools": ("Read", "Cat"),
    "pruning.reread_min_run_lines": 3,
    "pruning.reread_max_lines": 100,
    "compressors.log_filter.apply_to_verbatim_tools": True,
    "pruning.duplicate_min_tokens": 10,
    "pruning.duplicate_require_same_call": True,
    "tokens.default": "cl100k_base",
    "tokens.model_map": ({"pattern": "x-*", "tokenizer": "cl100k_base"},),
    "observability.trace_buffer": 10,
    "observability.response_header": False,
    "observability.log_format": "text",
    "observability.log_file": True,
    "telemetry.retention_days": 1,
}

# Behaviour-affecting defaults, written out from SPEC 017 "Keys added in S1" (CF-006).
DEFAULT_BEHAVIOUR_JSON = {
    "compression": {
        "segment_kinds": ["TOOL_RESULT", "USER_TEXT"],
        "verbatim_tools": ["Read", "Bash", "shell", "shell_command", "container.exec"],
        "min_segment_tokens": 64,
        "min_gain_tokens": 4,
        "min_gain_ratio": 0.01,
        "request_budget_ms": 50.0,
        "per_call_timeout_ms": 200.0,
        "verify_lossless": False,
        "result_cache_mb": 64,
    },
    "compressors": {
        "duplicate_tool_results": {"enabled": True},
        "json_minify": {"enabled": True},
        # S8a-1: the new compressors' default options enter the hash (CF-006).
        "search_group": {"enabled": False, "min_group_lines": 5, "apply_to_verbatim_tools": False},
        "log_filter": {"enabled": False, "debug_sample": 10, "apply_to_verbatim_tools": False},
        "edit_args_on_resume": {"enabled": False},  # S8c
        "reread_by_reference": {"enabled": True},  # S8e: on after its smoke record
    },
    "limits": {"max_transform_bytes": 33554432, "usage_parser_buffer": 1048576},
    "pruning": {
        "duplicate_min_tokens": 64,
        "duplicate_require_same_call": False,
        # S8c (SPEC 017 "Keys added in S8c")
        "resume_after_s": 3600.0,
        "resume_min_age_turns": 4,
        "resume_min_tokens": 64,
        "resume_edit_fields": {
            "Write": ["content"],
            "Edit": ["old_string", "new_string"],
            "MultiEdit": ["edits/*/old_string", "edits/*/new_string"],
        },
        "conversation_states": 1024,
        # S8e
        "reread_tools": ["Read"],
        "reread_min_run_lines": 5,
        "reread_max_lines": 20000,
    },
    "tokens": {
        "default": "o200k_base",
        "model_map": [
            {"pattern": "gpt-*", "tokenizer": "o200k_base"},
            {"pattern": "o*", "tokenizer": "o200k_base"},
            {"pattern": "claude-*", "tokenizer": "o200k_base"},
        ],
    },
}


def write_config(directory: Path, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "tokli.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def file_text(key: str, yaml_value: str) -> str:
    parts = key.split(".")
    lines = [f"{'  ' * depth}{part}:" for depth, part in enumerate(parts[:-1])]
    lines.append(f"{'  ' * (len(parts) - 1)}{parts[-1]}: {yaml_value}")
    return "\n".join(lines) + "\n"


def test_nested_keys_and_env_names() -> None:
    keys = schema_keys()
    assert (
        keys["compressors.json_minify.enabled"].env_var == "TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED"
    )
    assert keys["upstreams.anthropic.base_url"].env_var == "TOKLI_UPSTREAMS__ANTHROPIC__BASE_URL"
    assert keys["tls.ca_bundle"].text  # optional string: raw text in env and --set
    assert set(keys) == set(EXAMPLES)


def test_named_flag_source(env: dict[str, str]) -> None:
    config = load_config(
        CliOverrides(named=(("server.port", "9100", "--port"),)),
        {**env, "TOKLI_SERVER__PORT": "9000"},
        platform_name(),
    )
    assert config.values["server.port"] == 9100
    assert config.sources["server.port"] == "cli:--port"


def test_defaults_when_no_layers(env: dict[str, str]) -> None:
    config = load_config(CliOverrides(), env, platform_name())
    assert config.values["tokens.default"] == "o200k_base"
    assert set(config.sources.values()) == {"default"}
    assert config.config_file is None


@pytest.mark.parametrize("key", list(schema_keys()))
def test_env_overrides_file_for_every_key(env: dict[str, str], tmp_path: Path, key: str) -> None:
    file_value, env_value, expected = EXAMPLES[key]
    path = write_config(tmp_path / "cfg", file_text(key, file_value))

    from_file = load_config(CliOverrides(config_file=str(path)), env, platform_name())
    assert from_file.values[key] == FILE_EXPECTED[key]
    assert from_file.sources[key] == f"file:{path}"

    var = schema_keys()[key].env_var
    from_env = load_config(
        CliOverrides(config_file=str(path)), {**env, var: env_value}, platform_name()
    )
    assert from_env.values[key] == expected
    assert from_env.sources[key] == f"env:{var}"


@pytest.mark.parametrize("key", list(schema_keys()))
def test_set_flag_overrides_env(env: dict[str, str], key: str) -> None:
    info = schema_keys()[key]
    _, value, expected = EXAMPLES[key]
    other = EXAMPLES[key][0] if info.text else json.dumps(FILE_EXPECTED[key])
    config = load_config(
        CliOverrides(sets=(f"{key}={value}",)), {**env, info.env_var: other}, platform_name()
    )
    assert config.values[key] == expected
    assert config.sources[key] == "cli:--set"


def test_cli_overrides_env(env: dict[str, str], tmp_path: Path) -> None:
    env_file = write_config(tmp_path / "env-cfg", "tokens:\n  default: cl100k_base\n")
    flag_file = write_config(tmp_path / "flag-cfg", "tokens:\n  default: o200k_base\n")
    full_env = {**env, "TOKLI_CONFIG": str(env_file), "TOKLI_DATA_DIR": str(tmp_path / "d-env")}
    config = load_config(
        CliOverrides(config_file=str(flag_file), data_dir=str(tmp_path / "d-flag")),
        full_env,
        platform_name(),
    )
    assert config.config_file == flag_file
    assert config.config_file_source == "cli:--config"
    assert config.dirs.data_dir == tmp_path / "d-flag"
    assert config.values["tokens.default"] == "o200k_base"


def test_config_file_found_in_config_dir(env: dict[str, str], tmp_path: Path) -> None:
    cfg_dir = tmp_path / "cfgdir"
    path = write_config(cfg_dir, "tokens:\n  default: cl100k_base\n")
    config = load_config(CliOverrides(config_dir=str(cfg_dir)), env, platform_name())
    assert config.config_file == path
    assert config.config_file_source == "config dir"
    assert config.values["tokens.default"] == "cl100k_base"


def test_explicit_config_file_must_exist(env: dict[str, str], tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(config_file=str(tmp_path / "nope.yaml")), env, platform_name())
    assert "nope.yaml" in info.value.cause


def test_unknown_key_rejected_with_layer(env: dict[str, str], tmp_path: Path) -> None:
    path = write_config(tmp_path, "tokens:\n  defualt: o200k_base\n")
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(config_file=str(path)), env, platform_name())
    assert "tokens.defualt" in info.value.cause and str(path) in info.value.cause

    with pytest.raises(ConfigError) as info:
        load_config(
            CliOverrides(), {**env, "TOKLI_COMPRESION__POLICY": "LOSSY_ALLOWED"}, platform_name()
        )
    assert "TOKLI_COMPRESION__POLICY" in info.value.cause

    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(sets=("tokens.nope=1",)), env, platform_name())
    assert "tokens.nope" in info.value.cause and "--set" in info.value.cause


def test_unknown_section_rejected(env: dict[str, str], tmp_path: Path) -> None:
    path = write_config(tmp_path, "compression:\n  policy: LOSSLESS_ONLY\n")
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(config_file=str(path)), env, platform_name())
    assert "compression.policy" in info.value.cause


def test_invalid_value_names_layer_key_and_expected_type(
    env: dict[str, str], tmp_path: Path
) -> None:
    path = write_config(tmp_path, "tokens:\n  default: gpt2\n")
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(config_file=str(path)), env, platform_name())
    assert "tokens.default" in info.value.cause and str(path) in info.value.cause
    assert "o200k_base" in info.value.fix


def test_env_json_value_errors_name_variable(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(
            CliOverrides(), {**env, "TOKLI_TOKENS__MODEL_MAP": "[not json"}, platform_name()
        )
    assert "TOKLI_TOKENS__MODEL_MAP" in info.value.cause


def test_reserved_env_vars_only(env: dict[str, str], tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(), {**env, "TOKLI_FOO": "1"}, platform_name())
    assert "TOKLI_FOO" in info.value.cause
    reserved = {
        "TOKLI_DATA_DIR": str(tmp_path / "data"),
        "TOKLI_CONFIG_DIR": str(tmp_path / "cfg"),
        "TOKLI_DEBUG_CONTENT": "0",
    }
    config = load_config(CliOverrides(), {**env, **reserved}, platform_name())
    assert config.dirs.data_dir == tmp_path / "data"


def test_set_requires_key_equals_value(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(sets=("tokens.default",)), env, platform_name())
    assert "--set" in info.value.cause


def test_duplicate_yaml_key_rejected(env: dict[str, str], tmp_path: Path) -> None:
    path = write_config(tmp_path, "tokens:\n  default: o200k_base\n  default: cl100k_base\n")
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(config_file=str(path)), env, platform_name())
    assert "default" in info.value.cause and "duplicate" in info.value.cause


def test_yaml_implicit_types_rejected(env: dict[str, str], tmp_path: Path) -> None:
    # YAML 1.1 coercions are not applied: these stay strings.
    assert load_strict_yaml("a: yes\nb: on\nc: 2026-01-01\nd: 1:30\n", "t.yaml") == {
        "a": "yes",
        "b": "on",
        "c": "2026-01-01",
        "d": "1:30",
    }
    assert load_strict_yaml("a: true\nb: 12\nc: 1.5\nd: null\n", "t.yaml") == {
        "a": True,
        "b": 12,
        "c": 1.5,
        "d": None,
    }
    # A value whose YAML type does not match the schema type is an error, not a coercion.
    path = write_config(tmp_path, "tokens:\n  default: 12\n")
    with pytest.raises(ConfigError) as info:
        load_config(CliOverrides(config_file=str(path)), env, platform_name())
    assert "tokens.default" in info.value.cause


def test_empty_config_file_is_an_empty_layer(env: dict[str, str], tmp_path: Path) -> None:
    path = write_config(tmp_path, "")
    config = load_config(CliOverrides(config_file=str(path)), env, platform_name())
    assert set(config.sources.values()) == {"default"}


def test_config_snapshot_immutable(env: dict[str, str]) -> None:
    config = load_config(CliOverrides(), env, platform_name())
    with pytest.raises((AttributeError, TypeError)):
        config.values["tokens.default"] = "cl100k_base"  # type: ignore[index]
    with pytest.raises(ValidationError):
        config.settings.tokens.default = "cl100k_base"  # type: ignore[misc]
    assert isinstance(config.settings.tokens.model_map, tuple)
    with pytest.raises((AttributeError, TypeError)):
        config.sources["tokens.default"] = "cli:--set"  # type: ignore[index]


def test_config_hash_stable_and_sensitive(env: dict[str, str], tmp_path: Path) -> None:
    canonical = json.dumps(DEFAULT_BEHAVIOUR_JSON, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    config = load_config(CliOverrides(), env, platform_name())
    assert config.config_hash == expected

    # Paths and directories do not enter the hash.
    moved = load_config(
        CliOverrides(data_dir=str(tmp_path / "x"), config_dir=str(tmp_path / "y")),
        env,
        platform_name(),
    )
    assert moved.config_hash == expected

    changed = load_config(CliOverrides(sets=("tokens.default=cl100k_base",)), env, platform_name())
    assert changed.config_hash != expected


def test_cwd_config_and_dotenv_ignored(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "cwd"
    write_config(cwd, "tokens:\n  default: cl100k_base\n")
    (cwd / ".env").write_text("TOKLI_TOKENS__DEFAULT=cl100k_base\n", encoding="utf-8")
    monkeypatch.chdir(cwd)
    config = load_config(CliOverrides(), env, platform_name())
    assert config.values["tokens.default"] == "o200k_base"
    assert config.config_file is None


def test_keys_added_in_s2_defaults(env: dict[str, str]) -> None:
    """SPEC 017 "Keys added in S2" (AN-009, CC-024, OB-013)."""
    values = load_config(CliOverrides(), env, platform_name()).values
    assert values["limits.usage_parser_buffer"] == 1048576
    assert values["compression.result_cache_mb"] == 64
    assert values["observability.log_file"] is False


@pytest.mark.parametrize(
    "setting", ["compression.result_cache_mb=-1", "limits.usage_parser_buffer=0"]
)
def test_keys_added_in_s2_reject_out_of_range(env: dict[str, str], setting: str) -> None:
    with pytest.raises(ConfigError):
        load_config(CliOverrides(sets=(setting,)), env, platform_name())


def test_config_hash_changes_with_pruning_options(env: dict[str, str]) -> None:
    """S4 SCR-002: the `pruning` section is behaviour-affecting (CF-006)."""
    base = load_config(CliOverrides(), env, platform_name()).config_hash
    changed = load_config(
        CliOverrides(sets=("pruning.duplicate_min_tokens=128",)), env, platform_name()
    ).config_hash
    assert base != changed
