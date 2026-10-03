"""SPEC 017 layer 5 (UI overrides), CF-001, CF-002, CF-009 (S4; ADR 0009)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import platform_name
from tokli.config import CliOverrides, ConfigError, load_config, schema_keys
from tokli.config.loader import UI_OVERRIDES_FILE


def overrides(data_dir: Path, text: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / UI_OVERRIDES_FILE).write_text(text, encoding="utf-8")


def cfg(tmp_path: Path, env: dict[str, str], *sets: str, config: str | None = None):  # type: ignore[no-untyped-def]
    path = None
    if config is not None:
        path = tmp_path / "tokli.yaml"
        path.write_text(config, encoding="utf-8")
    return load_config(
        CliOverrides(
            config_file=str(path) if path else None, data_dir=str(tmp_path / "data"), sets=sets
        ),
        env,
        platform_name(),
    )


def test_keys_marked_ui_editable() -> None:
    """CF-009 after S4 SCR-001: compressor toggles and the retention period only."""
    editable = {k for k, info in schema_keys().items() if info.ui_editable}
    assert editable == {
        "compressors.json_minify.enabled",
        "compressors.duplicate_tool_results.enabled",
        "telemetry.retention_days",
    }


def test_ui_override_only_when_not_pinned(tmp_path: Path, env: dict[str, str]) -> None:
    """AC-CF-1: file < UI; env and CLI always win, and the key is reported locked."""
    overrides(tmp_path / "data", "compressors:\n  json_minify:\n    enabled: false\n")
    from_file = cfg(tmp_path, env, config="compressors:\n  json_minify:\n    enabled: true\n")
    assert from_file.values["compressors.json_minify.enabled"] is False
    assert from_file.sources["compressors.json_minify.enabled"] == "ui"
    assert "compressors.json_minify.enabled" not in from_file.locked

    pinned = cfg(tmp_path, {**env, "TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED": "true"})
    assert pinned.values["compressors.json_minify.enabled"] is True
    assert (
        pinned.locked["compressors.json_minify.enabled"]
        == "env:TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED"
    )

    by_cli = cfg(tmp_path, env, "compressors.json_minify.enabled=true")
    assert by_cli.values["compressors.json_minify.enabled"] is True
    assert by_cli.locked["compressors.json_minify.enabled"] == "cli:--set"


def test_ui_overrides_reject_non_editable_keys(tmp_path: Path, env: dict[str, str]) -> None:
    overrides(tmp_path / "data", "tokens:\n  default: cl100k_base\n")
    with pytest.raises(ConfigError) as info:
        cfg(tmp_path, env)
    assert "tokens.default" in info.value.cause and "ui" in info.value.cause


def test_ui_overrides_read_strictly(tmp_path: Path, env: dict[str, str]) -> None:
    overrides(tmp_path / "data", "telemetry:\n  retention_days: yes\n")
    with pytest.raises(ConfigError):
        cfg(tmp_path, env)


def test_ui_override_changes_config_hash(tmp_path: Path, env: dict[str, str]) -> None:
    before = cfg(tmp_path, env).config_hash
    overrides(tmp_path / "data", "compressors:\n  duplicate_tool_results:\n    enabled: false\n")
    after = cfg(tmp_path, env)
    assert after.config_hash != before
    assert after.settings.compressors.duplicate_tool_results.enabled is False


def test_config_reload_reads_new_overrides(tmp_path: Path, env: dict[str, str]) -> None:
    """ADR 0009: a snapshot can rebuild itself with the same CLI and environment."""
    config = cfg(tmp_path, env)
    overrides(tmp_path / "data", "telemetry:\n  retention_days: 7\n")
    assert config.reload().values["telemetry.retention_days"] == 7
    assert config.values["telemetry.retention_days"] == 30  # the old snapshot never changes
