"""Layered configuration loading (SPEC 017): defaults < file < environment < CLI.

The UI-override layer arrives in S4 (S0 review A1). A layer that sets a key replaces the key's
whole value. The merged document is validated once, in strict JSON mode, so the only accepted
types are the schema's (CF-003, CF-012).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from tokli.config.errors import ConfigError
from tokli.config.paths import ResolvedDirs, resolve_dirs
from tokli.config.schema import (
    BEHAVIOUR_SECTIONS,
    KeyInfo,
    TokliSettings,
    is_section,
    schema_keys,
)
from tokli.config.yamlfile import load_strict_yaml

# Environment variables that are not schema keys (SPEC 017, CF-011).
RESERVED_ENV: frozenset[str] = frozenset(
    {"TOKLI_CONFIG", "TOKLI_CONFIG_DIR", "TOKLI_DATA_DIR", "TOKLI_DEBUG_CONTENT"}
)

CONFIG_FILE_NAME = "tokli.yaml"
_KEYS_CACHE = frozenset(schema_keys())
_SHOW_FIX = "run 'tokli config show' to list valid settings"


@dataclass(frozen=True)
class CliOverrides:
    config_file: str | None = None
    config_dir: str | None = None
    data_dir: str | None = None
    sets: tuple[str, ...] = ()
    named: tuple[tuple[str, str, str], ...] = ()  # (key, raw value, flag), e.g. --port


@dataclass(frozen=True)
class EffectiveConfig:
    """Immutable snapshot of the effective configuration (CF-005)."""

    settings: TokliSettings
    sources: Mapping[str, str]
    values: Mapping[str, object]
    config_file: Path | None
    config_file_source: str | None
    dirs: ResolvedDirs
    config_hash: str


@dataclass(frozen=True)
class _Setting:
    value: object
    source: str


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(v) for v in value)
    return value


def _parse_text_value(info: KeyInfo, raw: str, origin: str) -> object:
    """Env and --set values: raw strings for text keys, JSON for everything else (CF-011)."""
    if info.text:
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            cause=f"{origin}: value for '{info.key}' is not valid JSON ({exc.msg})",
            fix="lists and maps are written as JSON, e.g. "
            '[{"pattern": "claude-*", "tokenizer": "o200k_base"}]',
        ) from exc


def _file_layer(path: Path, keys: Mapping[str, KeyInfo]) -> dict[str, _Setting]:
    source = f"file:{path}"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            cause=f"cannot read config file {path}: {exc.strerror or exc}",
            fix="check the path given by --config, TOKLI_CONFIG or the config dir",
        ) from exc
    document = load_strict_yaml(text, str(path))
    if document is None:
        return {}
    if not isinstance(document, dict):
        raise ConfigError(
            cause=f"{path}: the top level must be a mapping of sections",
            fix="write sections such as 'tokens:' with their keys indented below",
        )
    layer: dict[str, _Setting] = {}

    def walk(prefix: tuple[str, ...], node: dict[object, object]) -> None:
        for name, value in node.items():
            here = (*prefix, str(name))
            if is_section(here):
                if not isinstance(value, dict):
                    raise ConfigError(
                        cause=f"{path}: section '{'.'.join(here)}' must be a mapping of keys",
                        fix=_SHOW_FIX,
                    )
                walk(here, value)
                continue
            key = ".".join(here)
            if key not in keys:
                raise ConfigError(cause=f"{path}: unknown setting '{key}'", fix=_SHOW_FIX)
            layer[key] = _Setting(value, source)

    walk((), document)
    return layer


def _env_layer(env: Mapping[str, str], keys: Mapping[str, KeyInfo]) -> dict[str, _Setting]:
    by_var = {info.env_var: info for info in keys.values()}
    layer: dict[str, _Setting] = {}
    for var in sorted(env):
        if not var.startswith("TOKLI_") or var in RESERVED_ENV:
            continue
        info = by_var.get(var)
        if info is None:
            raise ConfigError(
                cause=f"environment variable {var} is not a Tokli setting",
                fix=f"unset it or check the spelling; {_SHOW_FIX}",
            )
        layer[info.key] = _Setting(_parse_text_value(info, env[var], f"env:{var}"), f"env:{var}")
    return layer


def _cli_layer(
    sets: tuple[str, ...],
    named: tuple[tuple[str, str, str], ...],
    keys: Mapping[str, KeyInfo],
) -> dict[str, _Setting]:
    layer: dict[str, _Setting] = {}
    for key, raw, flag in named:
        named_info = keys[key]
        layer[key] = _Setting(_parse_text_value(named_info, raw, f"cli:{flag}"), f"cli:{flag}")
    for item in sets:
        key, sep, raw = item.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ConfigError(
                cause=f"cli:--set '{item}' is not of the form section.key=value",
                fix="write --set tokens.default=o200k_base",
            )
        info = keys.get(key)
        if info is None:
            raise ConfigError(cause=f"cli:--set: unknown setting '{key}'", fix=_SHOW_FIX)
        layer[key] = _Setting(_parse_text_value(info, raw, "cli:--set"), "cli:--set")
    return layer


def _locate_config_file(
    cli: CliOverrides, env: Mapping[str, str], dirs: ResolvedDirs
) -> tuple[Path | None, str | None]:
    explicit = [(cli.config_file, "cli:--config"), (env.get("TOKLI_CONFIG"), "env:TOKLI_CONFIG")]
    for value, source in explicit:
        if value:
            path = Path(value)
            if not path.is_file():
                raise ConfigError(
                    cause=f"config file not found: {path} (from {source})",
                    fix="create the file or correct the path",
                )
            return path, source
    candidate = dirs.config_dir / CONFIG_FILE_NAME
    if candidate.is_file():
        return candidate, "config dir"
    return None, None


def _validate(merged: dict[str, _Setting], defaults: TokliSettings) -> TokliSettings:
    document: dict[str, Any] = defaults.model_dump(mode="json")
    for key, setting in merged.items():
        *parents, name = key.split(".")
        node = document
        for part in parents:
            node = node[part]
        node[name] = setting.value
    try:
        payload = json.dumps(document, allow_nan=False)
    except (TypeError, ValueError) as exc:
        bad = next((k for k, s in merged.items() if not _json_ok(s.value)), "a setting")
        source = merged[bad].source if bad in merged else "configuration"
        raise ConfigError(
            cause=f"{source}: value for '{bad}' has an unsupported type",
            fix="use strings, numbers, true/false, lists and mappings only",
        ) from exc
    try:
        return TokliSettings.model_validate_json(payload, strict=True)
    except ValidationError as exc:
        error = exc.errors()[0]
        loc = [str(part) for part in error["loc"]]
        key = next(
            (".".join(loc[:n]) for n in range(len(loc), 0, -1) if ".".join(loc[:n]) in _KEYS_CACHE),
            ".".join(loc),
        )
        source = merged[key].source if key in merged else "default"
        where = ".".join(loc)
        raise ConfigError(
            cause=f"{source}: invalid value for '{key}' at {where}: {error['msg']}",
            fix=f"expected: {_expected(error)}",
        ) from exc


def _lookup(document: Mapping[str, Any], key: str) -> object:
    node: Any = document
    for part in key.split("."):
        node = node[part]
    return node


def _json_ok(value: object) -> bool:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return True


def _expected(error: Mapping[str, object]) -> str:
    ctx = error.get("ctx")
    if isinstance(ctx, dict) and "expected" in ctx:
        return str(ctx["expected"])
    return str(error.get("msg", "a value of the schema type"))


def _config_hash(settings: TokliSettings) -> str:
    dumped = settings.model_dump(mode="json")
    behaviour = {section: dumped[section] for section in BEHAVIOUR_SECTIONS}
    canonical = json.dumps(behaviour, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_config(cli: CliOverrides, env: Mapping[str, str], platform: str) -> EffectiveConfig:
    """Resolve every setting by precedence and return an immutable snapshot."""
    keys = schema_keys()
    dirs = resolve_dirs(
        cli_config_dir=cli.config_dir, cli_data_dir=cli.data_dir, env=env, platform=platform
    )
    config_file, config_file_source = _locate_config_file(cli, env, dirs)

    merged: dict[str, _Setting] = {}
    if config_file is not None:
        merged.update(_file_layer(config_file, keys))
    merged.update(_env_layer(env, keys))
    merged.update(_cli_layer(cli.sets, cli.named, keys))

    defaults = TokliSettings()
    settings = _validate(merged, defaults)
    dumped = settings.model_dump(mode="json")
    values = {key: _freeze(_lookup(dumped, key)) for key in keys}
    sources = {key: merged[key].source if key in merged else "default" for key in keys}
    return EffectiveConfig(
        settings=settings,
        sources=MappingProxyType(sources),
        values=MappingProxyType(values),
        config_file=config_file,
        config_file_source=config_file_source,
        dirs=dirs,
        config_hash=_config_hash(settings),
    )
