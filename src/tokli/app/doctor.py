"""``tokli doctor`` (PT-005 S0 subset, PT-007, PT-008, PT-012, TM-006).

The report never contains credential values or file contents: it prints only settings from the
schema, paths and hashes. The normalized rendering drops everything that legitimately differs
between machines (paths, Python, OS, build), so it can be compared across installs (AC-PT-7).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tokli.app.setup_tokenizers import required_tokenizers
from tokli.config import EffectiveConfig
from tokli.tokens import CATALOG, TokenizerSpec, TokenizerState, TokenizerStatus, check_tokenizer

SETUP_FIX = "run 'tokli setup tokenizers'"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    cause: str = ""
    fix: str = ""


@dataclass(frozen=True)
class Environment:
    tokli_version: str
    python: str
    platform: str


@dataclass(frozen=True)
class DoctorReport:
    environment: Environment
    config: EffectiveConfig
    tokenizers: tuple[TokenizerStatus, ...]
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


def _is_writable(path: Path) -> bool:
    """Whether ``path`` exists as a writable directory or could be created. Writes nothing."""
    candidate = path
    while not candidate.exists():
        if candidate.parent == candidate:
            return False
        candidate = candidate.parent
    return candidate.is_dir() and os.access(candidate, os.W_OK)


def _data_dir_check(config: EffectiveConfig) -> Check:
    data_dir = config.dirs.data_dir
    if _is_writable(data_dir):
        return Check("data dir writable", True)
    return Check(
        "data dir writable",
        False,
        cause=f"data dir is not writable: {data_dir}",
        fix="choose another directory with --data-dir or TOKLI_DATA_DIR",
    )


def _tokenizer_check(status: TokenizerStatus) -> Check:
    name = f"tokenizer {status.spec.name} present"
    if status.state is TokenizerState.PRESENT:
        return Check(name, True)
    if status.state is TokenizerState.MISSING:
        cause = f"tokenizer {status.spec.name} missing: expected {status.path}"
    else:
        cause = f"tokenizer {status.spec.name} hash mismatch: {status.path} is not the pinned file"
    return Check(name, False, cause=cause, fix=SETUP_FIX)


def build_report(
    config: EffectiveConfig,
    environment: Environment,
    catalog: Mapping[str, TokenizerSpec] = CATALOG,
) -> DoctorReport:
    statuses = tuple(
        check_tokenizer(catalog[name], config.dirs.data_dir)
        for name in required_tokenizers(config.settings)
    )
    checks = (_data_dir_check(config), *(_tokenizer_check(s) for s in statuses))
    return DoctorReport(environment, config, statuses, checks)


def _source(source: str, normalized: bool) -> str:
    if normalized and source.startswith("file:"):
        return "file"
    return source


def config_lines(config: EffectiveConfig, *, normalized: bool) -> list[str]:
    dumped = config.settings.model_dump(mode="json")
    lines = []
    for key, source in config.sources.items():
        section, name = key.split(".", 1)
        value = json.dumps(dumped[section][name], ensure_ascii=True)
        lines.append(f"  {key} = {value}  [{_source(source, normalized)}]")
    return lines


def render(report: DoctorReport, *, normalized: bool) -> str:
    config = report.config
    out: list[str] = ["Tokli doctor (normalized)" if normalized else "Tokli doctor", ""]

    if not normalized:
        env = report.environment
        config_file = (
            f"{config.config_file}  [{config.config_file_source}]"
            if config.config_file is not None
            else "(none)"
        )
        out += [
            "Environment",
            f"  {'tokli version':<15}{env.tokli_version}",
            f"  {'python':<15}{env.python}",
            f"  {'platform':<15}{env.platform}",
            f"  {'config dir':<15}{config.dirs.config_dir}  [{config.dirs.config_dir_source}]",
            f"  {'config file':<15}{config_file}",
            f"  {'data dir':<15}{config.dirs.data_dir}  [{config.dirs.data_dir_source}]",
            "",
        ]

    out.append(f"Configuration  hash {config.config_hash[:16]}")
    out += config_lines(config, normalized=normalized)
    out += ["", "Tokenizers"]
    for status in report.tokenizers:
        line = f"  {status.spec.name}  {status.state.value}  {status.spec.tokenizer_id}"
        out.append(line if normalized else f"{line}  {status.path}")
    out += ["", "Checks"]
    for check in report.checks:
        out.append(f"  {'[ok]  ' if check.ok else '[FAIL]'} {check.name}")
        if not check.ok and not normalized:
            out.append(f"         cause: {check.cause}")
            out.append(f"         fix:   {check.fix}")

    failed = sum(not check.ok for check in report.checks)
    result = (
        "all checks passed" if failed == 0 else f"{failed} check{'s' if failed > 1 else ''} failed"
    )
    out += ["", f"Result: {result}"]
    return "\n".join(out) + "\n"
