"""Config and data directory resolution (CF-008, MD-04, MD-07). Never uses the working directory.

Resolution is a pure function of the flags, the environment mapping and the platform name, so it
can be tested for every platform on any machine.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tokli.config.errors import ConfigError


@dataclass(frozen=True)
class ResolvedDirs:
    config_dir: Path
    config_dir_source: str
    data_dir: Path
    data_dir_source: str


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value:
        raise ConfigError(
            cause=f"cannot determine the default directories: {name} is not set",
            fix="pass --config-dir and --data-dir (or set TOKLI_CONFIG_DIR and TOKLI_DATA_DIR)",
        )
    return value


def _home(env: Mapping[str, str], platform: str) -> Path:
    return Path(_require(env, "USERPROFILE" if platform == "win32" else "HOME"))


def _default_config_dir(env: Mapping[str, str], platform: str) -> Path:
    if platform == "win32":
        return Path(_require(env, "APPDATA"), "Tokli")
    if platform == "darwin":
        return _home(env, platform) / "Library" / "Application Support" / "Tokli"
    xdg = env.get("XDG_CONFIG_HOME", "")
    return (Path(xdg) if xdg else _home(env, platform) / ".config") / "tokli"


def _default_data_dir(env: Mapping[str, str], platform: str) -> Path:
    if platform == "win32":
        return Path(_require(env, "LOCALAPPDATA"), "Tokli")
    if platform == "darwin":
        return _home(env, platform) / "Library" / "Application Support" / "Tokli"
    xdg = env.get("XDG_DATA_HOME", "")
    return (Path(xdg) if xdg else _home(env, platform) / ".local" / "share") / "tokli"


def resolve_dirs(
    *,
    cli_config_dir: str | None,
    cli_data_dir: str | None,
    env: Mapping[str, str],
    platform: str,
) -> ResolvedDirs:
    if cli_config_dir:
        config_dir, config_source = Path(cli_config_dir), "cli:--config-dir"
    elif env.get("TOKLI_CONFIG_DIR"):
        config_dir, config_source = Path(env["TOKLI_CONFIG_DIR"]), "env:TOKLI_CONFIG_DIR"
    else:
        config_dir, config_source = _default_config_dir(env, platform), "default"

    if cli_data_dir:
        data_dir, data_source = Path(cli_data_dir), "cli:--data-dir"
    elif env.get("TOKLI_DATA_DIR"):
        data_dir, data_source = Path(env["TOKLI_DATA_DIR"]), "env:TOKLI_DATA_DIR"
    else:
        data_dir, data_source = _default_data_dir(env, platform), "default"

    return ResolvedDirs(config_dir, config_source, data_dir, data_source)
