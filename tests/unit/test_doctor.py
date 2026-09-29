"""PT-005 (S0 subset), PT-007, PT-008, PT-012, TM-006: the doctor report."""

from __future__ import annotations

import platform
import shutil
import socket
from pathlib import Path

import pytest

from tests.conftest import Cli
from tests.helpers import (
    FAKE_CATALOG,
    FAKE_SPEC,
    FAKE_TOKENIZER_BYTES,
    PROVISIONED_DATA_DIR,
    normalize_newlines,
    platform_name,
    read_golden,
)
from tokli.app.doctor import Environment, build_report, render
from tokli.config import CliOverrides, load_config
from tokli.tokens import tokenizer_dir

ENV = Environment(tokli_version="9.9.9", python="3.11.0 (CPython)", platform="TestOS 1 x86_64")


def provision_fake(data_dir: Path) -> None:
    target = tokenizer_dir(data_dir) / FAKE_SPEC.filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(FAKE_TOKENIZER_BYTES)


def test_doctor_report_fields(env: dict[str, str], tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    provision_fake(data_dir)
    config = load_config(CliOverrides(data_dir=str(data_dir)), env, platform_name())
    report = build_report(config, ENV, catalog=FAKE_CATALOG)
    assert report.ok
    text = render(report, normalized=False)
    for expected in (
        "tokli version  9.9.9",
        "python         3.11.0 (CPython)",
        "platform       TestOS 1 x86_64",
        f"config dir     {config.dirs.config_dir}  [default]",
        "config file    (none)",
        f"data dir       {data_dir}  [cli:--data-dir]",
        'tokens.default = "o200k_base"  [default]',
        f"Configuration  hash {config.config_hash[:16]}",
        f"o200k_base  present  {FAKE_SPEC.tokenizer_id}",
        "[ok]   data dir writable",
        "[ok]   tokenizer o200k_base present",
        "Result: all checks passed",
    ):
        assert expected in text, expected


def test_missing_tokenizer_fails_with_actionable_message(
    env: dict[str, str], tmp_path: Path
) -> None:
    data_dir = tmp_path / "data"
    config = load_config(CliOverrides(data_dir=str(data_dir)), env, platform_name())
    report = build_report(config, ENV, catalog=FAKE_CATALOG)
    assert not report.ok
    failed = [c for c in report.checks if not c.ok]
    assert [c.name for c in failed] == ["tokenizer o200k_base present"]
    expected_path = tokenizer_dir(data_dir) / FAKE_SPEC.filename
    assert failed[0].cause == f"tokenizer o200k_base missing: expected {expected_path}"
    assert failed[0].fix == "run 'tokli setup tokenizers'"
    text = render(report, normalized=False)
    assert f"expected {expected_path}" in text and "run 'tokli setup tokenizers'" in text


def test_tampered_tokenizer_is_reported(env: dict[str, str], tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    provision_fake(data_dir)
    (tokenizer_dir(data_dir) / FAKE_SPEC.filename).write_bytes(b"changed")
    config = load_config(CliOverrides(data_dir=str(data_dir)), env, platform_name())
    report = build_report(config, ENV, catalog=FAKE_CATALOG)
    failed = [c for c in report.checks if not c.ok]
    assert "hash mismatch" in failed[0].cause


def test_unwritable_data_dir_reported(env: dict[str, str], tmp_path: Path) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    config = load_config(CliOverrides(data_dir=str(blocker / "data")), env, platform_name())
    report = build_report(config, ENV, catalog=FAKE_CATALOG)
    failed = {c.name: c for c in report.checks if not c.ok}
    assert "data dir writable" in failed
    assert str(blocker / "data") in failed["data dir writable"].cause
    assert "--data-dir" in failed["data dir writable"].fix


def test_doctor_reports_python_version(cli: Cli) -> None:
    result = cli.run("doctor")
    assert platform.python_version() in result.out


def test_doctor_exit_codes(cli: Cli, tmp_path: Path) -> None:
    assert cli.run("doctor").code == 1  # the real tokenizer is not provisioned here


def test_doctor_normalised_snapshot(cli: Cli) -> None:
    result = cli.run("doctor", "--normalized")
    assert result.code == 1
    assert normalize_newlines(result.out) == read_golden("doctor_normalized_missing.txt")


@pytest.mark.skipif(PROVISIONED_DATA_DIR is None, reason="set TEST_TOKLI_PROVISIONED_DATA_DIR")
def test_doctor_normalised_snapshot_provisioned(cli: Cli, tmp_path: Path) -> None:
    assert PROVISIONED_DATA_DIR is not None
    data_dir = tmp_path / "provisioned"
    shutil.copytree(Path(PROVISIONED_DATA_DIR) / "tokenizers", data_dir / "tokenizers")
    result = cli.run("doctor", "--normalized", "--data-dir", str(data_dir))
    assert result.code == 0, result.out
    assert normalize_newlines(result.out) == read_golden("doctor_normalized_provisioned.txt")


def test_doctor_never_prints_secrets(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    canaries = {
        "ANTHROPIC_API_KEY": "sk-ant-api03-TOKLI-CANARY-1",
        "OPENAI_API_KEY": "sk-proj-TOKLI-CANARY-2",
        "ANTHROPIC_AUTH_TOKEN": "TOKLI-CANARY-3",
    }
    for name, value in canaries.items():
        monkeypatch.setenv(name, value)
    result = cli.run("doctor")
    for value in canaries.values():
        assert value not in result.out and value not in result.err


def test_doctor_makes_no_network_calls(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    result = cli.run("doctor")
    assert result.code == 1  # tokenizer missing, but no network was used
    assert "Result:" in result.out


def test_starts_offline_with_provisioned_tokenizer(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    data_dir = tmp_path / "data"
    provision_fake(data_dir)
    config = load_config(CliOverrides(data_dir=str(data_dir)), env, platform_name())
    assert build_report(config, ENV, catalog=FAKE_CATALOG).ok


def test_invalid_config_fails_clearly(cli: Cli) -> None:
    config = cli.workdir / "bad.yaml"
    config.write_text("tokens:\n  defualt: o200k_base\n", encoding="utf-8")
    result = cli.run("doctor", "--config", str(config))
    assert result.code == 1
    lines = result.err.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("error: ") and "tokens.defualt" in lines[0]
    assert lines[1].startswith("fix: ")
