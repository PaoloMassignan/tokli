"""TM-010, PT-003: `tokli setup tokenizers` provisions only verified files."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import FAKE_CATALOG, FAKE_SPEC, FAKE_TOKENIZER_BYTES, platform_name
from tokli.app.setup_tokenizers import required_tokenizers, setup_tokenizers
from tokli.config import CliOverrides, ConfigError, load_config
from tokli.tokens import TokenizerSpec, tokenizer_dir


def config_with_data_dir(env: dict[str, str], data_dir: Path, *sets: str):  # type: ignore[no-untyped-def]
    return load_config(CliOverrides(data_dir=str(data_dir), sets=sets), env, platform_name())


def no_network(url: str) -> bytes:
    raise AssertionError(f"network used: {url}")


def test_required_tokenizers(env: dict[str, str], tmp_path: Path) -> None:
    assert required_tokenizers(config_with_data_dir(env, tmp_path).settings) == ("o200k_base",)
    both = config_with_data_dir(
        env,
        tmp_path,
        'tokens.model_map=[{"pattern": "x-*", "tokenizer": "cl100k_base"}]',
    )
    assert required_tokenizers(both.settings) == ("cl100k_base", "o200k_base")


def test_setup_tokenizers_verifies_sha256(env: dict[str, str], tmp_path: Path) -> None:
    config = config_with_data_dir(env, tmp_path / "data")
    target = tokenizer_dir(tmp_path / "data") / FAKE_SPEC.filename
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return FAKE_TOKENIZER_BYTES

    results = setup_tokenizers(config, fetch=fetch, catalog=FAKE_CATALOG)
    assert [(r.name, r.action) for r in results] == [("o200k_base", "downloaded")]
    assert fetched == [FAKE_SPEC.url]
    assert target.read_bytes() == FAKE_TOKENIZER_BYTES

    again = setup_tokenizers(config, fetch=no_network, catalog=FAKE_CATALOG)
    assert [(r.name, r.action) for r in again] == [("o200k_base", "already present")]


def test_setup_tokenizers_refuses_tampered_download(env: dict[str, str], tmp_path: Path) -> None:
    config = config_with_data_dir(env, tmp_path / "data")
    with pytest.raises(ConfigError) as info:
        setup_tokenizers(config, fetch=lambda url: b"tampered", catalog=FAKE_CATALOG)
    assert "SHA-256" in info.value.cause
    assert not (tokenizer_dir(tmp_path / "data") / FAKE_SPEC.filename).exists()


def test_setup_tokenizers_from_file(env: dict[str, str], tmp_path: Path) -> None:
    source = tmp_path / "downloads" / "any-name.bin"
    source.parent.mkdir()
    source.write_bytes(FAKE_TOKENIZER_BYTES)
    config = config_with_data_dir(env, tmp_path / "data")

    results = setup_tokenizers(config, fetch=no_network, from_files=[source], catalog=FAKE_CATALOG)
    assert [(r.name, r.action) for r in results] == [("o200k_base", "copied")]
    assert (
        tokenizer_dir(tmp_path / "data") / FAKE_SPEC.filename
    ).read_bytes() == FAKE_TOKENIZER_BYTES


def test_setup_tokenizers_from_file_rejects_unknown_file(
    env: dict[str, str], tmp_path: Path
) -> None:
    source = tmp_path / "random.bin"
    source.write_bytes(b"not a tokenizer")
    config = config_with_data_dir(env, tmp_path / "data")
    with pytest.raises(ConfigError) as info:
        setup_tokenizers(config, fetch=no_network, from_files=[source], catalog=FAKE_CATALOG)
    assert "random.bin" in info.value.cause


def test_setup_tokenizers_from_file_never_downloads_missing_ones(
    env: dict[str, str], tmp_path: Path
) -> None:
    other = tmp_path / "other.bin"
    other.write_bytes(FAKE_TOKENIZER_BYTES)
    config = config_with_data_dir(
        env,
        tmp_path / "data",
        'tokens.model_map=[{"pattern": "x-*", "tokenizer": "cl100k_base"}]',
    )
    catalog = {
        **FAKE_CATALOG,
        "cl100k_base": TokenizerSpec(
            name="cl100k_base",
            filename="cl100k_base.tiktoken",
            url="https://tokenizers.invalid/cl100k_base.tiktoken",
            sha256="0" * 64,
        ),
    }
    with pytest.raises(ConfigError) as info:
        setup_tokenizers(config, fetch=no_network, from_files=[other], catalog=catalog)
    assert "cl100k_base" in info.value.cause


def test_unwritable_data_dir_fails_clearly(env: dict[str, str], tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    config = config_with_data_dir(env, blocker / "data")
    with pytest.raises(ConfigError) as info:
        setup_tokenizers(config, fetch=lambda url: FAKE_TOKENIZER_BYTES, catalog=FAKE_CATALOG)
    assert str(blocker / "data") in info.value.cause
    assert "--data-dir" in info.value.fix
