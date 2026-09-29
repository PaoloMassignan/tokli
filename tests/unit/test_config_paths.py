"""CF-008, MD-07: config and data directories per platform, overridable, never the CWD."""

from __future__ import annotations

from pathlib import Path

import pytest

from tokli.config import ConfigError, resolve_dirs

# (platform, env var of the config dir default, suffix, env var of the data dir default, suffix)
PLATFORMS = [
    ("win32", "APPDATA", ("Tokli",), "LOCALAPPDATA", ("Tokli",)),
    (
        "darwin",
        "HOME",
        ("Library", "Application Support", "Tokli"),
        "HOME",
        ("Library", "Application Support", "Tokli"),
    ),
    ("linux", "XDG_CONFIG_HOME", ("tokli",), "XDG_DATA_HOME", ("tokli",)),
]


@pytest.mark.parametrize(
    ("platform", "cfg_var", "cfg_suffix", "data_var", "data_suffix"), PLATFORMS
)
def test_data_dir_resolution_per_platform(
    env: dict[str, str],
    platform: str,
    cfg_var: str,
    cfg_suffix: tuple[str, ...],
    data_var: str,
    data_suffix: tuple[str, ...],
) -> None:
    dirs = resolve_dirs(cli_config_dir=None, cli_data_dir=None, env=env, platform=platform)
    assert dirs.data_dir == Path(env[data_var], *data_suffix)
    assert dirs.data_dir_source == "default"

    env_override = {**env, "TOKLI_DATA_DIR": str(Path(env["HOME"], "from-env"))}
    dirs = resolve_dirs(cli_config_dir=None, cli_data_dir=None, env=env_override, platform=platform)
    assert dirs.data_dir == Path(env["HOME"], "from-env")
    assert dirs.data_dir_source == "env:TOKLI_DATA_DIR"

    flag = str(Path(env["HOME"], "from-flag"))
    dirs = resolve_dirs(cli_config_dir=None, cli_data_dir=flag, env=env_override, platform=platform)
    assert dirs.data_dir == Path(flag)
    assert dirs.data_dir_source == "cli:--data-dir"


@pytest.mark.parametrize(
    ("platform", "cfg_var", "cfg_suffix", "data_var", "data_suffix"), PLATFORMS
)
def test_config_dir_resolution_per_platform(
    env: dict[str, str],
    platform: str,
    cfg_var: str,
    cfg_suffix: tuple[str, ...],
    data_var: str,
    data_suffix: tuple[str, ...],
) -> None:
    dirs = resolve_dirs(cli_config_dir=None, cli_data_dir=None, env=env, platform=platform)
    assert dirs.config_dir == Path(env[cfg_var], *cfg_suffix)
    assert dirs.config_dir_source == "default"

    env_override = {**env, "TOKLI_CONFIG_DIR": str(Path(env["HOME"], "cfg-env"))}
    dirs = resolve_dirs(cli_config_dir=None, cli_data_dir=None, env=env_override, platform=platform)
    assert dirs.config_dir == Path(env["HOME"], "cfg-env")
    assert dirs.config_dir_source == "env:TOKLI_CONFIG_DIR"

    flag = str(Path(env["HOME"], "cfg-flag"))
    dirs = resolve_dirs(cli_config_dir=flag, cli_data_dir=None, env=env_override, platform=platform)
    assert dirs.config_dir == Path(flag)
    assert dirs.config_dir_source == "cli:--config-dir"


def test_linux_xdg_fallbacks_use_home(env: dict[str, str]) -> None:
    bare = {"HOME": env["HOME"]}
    dirs = resolve_dirs(cli_config_dir=None, cli_data_dir=None, env=bare, platform="linux")
    assert dirs.config_dir == Path(env["HOME"], ".config", "tokli")
    assert dirs.data_dir == Path(env["HOME"], ".local", "share", "tokli")


def test_missing_home_fails_clearly() -> None:
    with pytest.raises(ConfigError) as info:
        resolve_dirs(cli_config_dir=None, cli_data_dir=None, env={}, platform="linux")
    assert "--data-dir" in info.value.fix
