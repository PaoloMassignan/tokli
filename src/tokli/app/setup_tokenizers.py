"""``tokli setup tokenizers`` (TM-010, PT-003): the only command that may use the network.

Files are verified against the pinned SHA-256 before anything is written, and written
atomically, so a failed or tampered download never leaves a file behind.
"""

from __future__ import annotations

import os
import tempfile
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tokli.config import ConfigError, EffectiveConfig, TokliSettings
from tokli.tokens import CATALOG, TokenizerSpec, TokenizerState, check_tokenizer, sha256_hex

Fetch = Callable[[str], bytes]

_DOWNLOAD_TIMEOUT_S = 60


@dataclass(frozen=True)
class SetupResult:
    name: str
    action: str  # "already present" | "downloaded" | "copied"
    path: Path


def required_tokenizers(settings: TokliSettings) -> tuple[str, ...]:
    """Tokenizer names referenced by the configuration, sorted and unique."""
    names = {settings.tokens.default}
    names.update(entry.tokenizer for entry in settings.tokens.model_map)
    return tuple(sorted(names))


def urllib_fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as response:
        data: bytes = response.read()
        return data


def _write_atomically(target: Path, data: bytes, data_dir: Path) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".partial-")
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, target)
    except OSError as exc:
        raise ConfigError(
            cause=f"data dir is not writable: {data_dir} ({exc.strerror or exc})",
            fix="choose another directory with --data-dir or TOKLI_DATA_DIR",
        ) from exc


def setup_tokenizers(
    config: EffectiveConfig,
    *,
    fetch: Fetch = urllib_fetch,
    from_files: Sequence[Path] = (),
    catalog: Mapping[str, TokenizerSpec] = CATALOG,
) -> list[SetupResult]:
    data_dir = config.dirs.data_dir
    specs = [catalog[name] for name in required_tokenizers(config.settings)]

    offline: dict[str, bytes] = {}
    for path in from_files:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ConfigError(
                cause=f"cannot read {path}: {exc.strerror or exc}",
                fix="check the path given to --from-file",
            ) from exc
        digest = sha256_hex(data)
        match = next((spec for spec in specs if spec.sha256 == digest), None)
        if match is None:
            raise ConfigError(
                cause=f"{path} does not match the pinned SHA-256 of any required tokenizer "
                f"({', '.join(spec.name for spec in specs)})",
                fix="pass the original .tiktoken file published for that tokenizer",
            )
        offline[match.name] = data

    results: list[SetupResult] = []
    for spec in specs:
        status = check_tokenizer(spec, data_dir)
        if status.state is TokenizerState.PRESENT:
            results.append(SetupResult(spec.name, "already present", status.path))
            continue
        if from_files:
            if spec.name not in offline:
                raise ConfigError(
                    cause=f"tokenizer {spec.name} is required but no --from-file matches it",
                    fix=f"add --from-file for {spec.filename}, "
                    "or run without --from-file to download",
                )
            data, action = offline[spec.name], "copied"
        else:
            try:
                data = fetch(spec.url)
            except OSError as exc:
                raise ConfigError(
                    cause=f"download of {spec.name} from {spec.url} failed: {exc}",
                    fix="check the network, or download the file elsewhere and use --from-file",
                ) from exc
            action = "downloaded"
            if sha256_hex(data) != spec.sha256:
                raise ConfigError(
                    cause=f"downloaded {spec.name} does not match its pinned SHA-256; "
                    "nothing was stored",
                    fix="retry later; if it persists, the published file changed "
                    "and Tokli must be updated",
                )
        _write_atomically(status.path, data, data_dir)
        results.append(SetupResult(spec.name, action, status.path))
    return results
