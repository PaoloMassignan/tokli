"""Configuration: schema, layered precedence and effective snapshot (SPEC 017)."""

from tokli.config.errors import ConfigError
from tokli.config.loader import RESERVED_ENV, CliOverrides, EffectiveConfig, load_config
from tokli.config.paths import ResolvedDirs, resolve_dirs
from tokli.config.schema import KeyInfo, TokenizerName, TokliSettings, schema_keys

__all__ = [
    "RESERVED_ENV",
    "CliOverrides",
    "ConfigError",
    "EffectiveConfig",
    "KeyInfo",
    "ResolvedDirs",
    "TokenizerName",
    "TokliSettings",
    "load_config",
    "resolve_dirs",
    "schema_keys",
]
