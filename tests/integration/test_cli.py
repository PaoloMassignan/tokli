"""CLI behaviour and fresh-machine properties that apply without a server (S0 review X3)."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests.conftest import Cli
from tests.helpers import FAKE_TOKENIZER_BYTES, home_env


def listing(directory: Path) -> set[str]:
    return {str(p.relative_to(directory)) for p in directory.rglob("*")}


def test_config_show_reports_sources(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKLI_TOKENS__DEFAULT", "cl100k_base")
    result = cli.run("config", "show")
    assert result.code == 0, result.err
    assert 'tokens.default = "cl100k_base"  [env:TOKLI_TOKENS__DEFAULT]' in result.out
    assert "tokens.model_map = " in result.out and "[default]" in result.out
    assert "config hash: " in result.out

    result = cli.run("config", "show", "--set", "tokens.default=o200k_base")
    assert 'tokens.default = "o200k_base"  [cli:--set]' in result.out


def test_cli_output_encodable_cp1252(cli: Cli) -> None:
    for argv in (("doctor",), ("doctor", "--normalized"), ("config", "show")):
        result = cli.run(*argv)
        (result.out + result.err).encode("cp1252")


def test_behaviour_independent_of_cwd(
    cli: Cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = []
    for name in ("one", "two"):
        cwd = tmp_path / name
        cwd.mkdir()
        (cwd / "tokli.yaml").write_text("tokens:\n  default: cl100k_base\n", encoding="utf-8")
        before = listing(cwd)
        monkeypatch.chdir(cwd)
        outputs.append(cli.run("doctor", "--normalized").out)
        cli.run("config", "show")
        assert listing(cwd) == before  # nothing written to the working directory
    assert outputs[0] == outputs[1]
    assert '"o200k_base"' in outputs[0]  # the CWD tokli.yaml was ignored


def test_temp_home_clean_start(cli: Cli) -> None:
    result = cli.run("doctor")
    assert str(cli.home) in result.out  # both default dirs live under the temporary HOME
    assert "[ok]   data dir writable" in result.out
    assert not (cli.home).exists() or listing(cli.home) == set()  # doctor creates nothing


def test_setup_tokenizers_cli_refuses_unknown_file(cli: Cli) -> None:
    source = cli.workdir / "file.bin"
    source.write_bytes(FAKE_TOKENIZER_BYTES)
    result = cli.run("setup", "tokenizers", "--from-file", str(source))
    assert result.code == 1  # not the real o200k_base file: refused, nothing stored
    assert "file.bin" in result.err


def test_hostile_environment_ignored(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = cli.run("doctor", "--normalized").out
    monkeypatch.setenv("ANTHROPIC_API_KEY", "junk")
    monkeypatch.setenv("OPENAI_API_KEY", "junk")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://example.invalid")
    assert cli.run("doctor", "--normalized").out == baseline

    monkeypatch.setenv("TOKLI_TOKENS__DEFAULT", "gpt2")
    result = cli.run("doctor")
    assert result.code == 1
    assert "TOKLI_TOKENS__DEFAULT" in result.err


def test_import_has_no_side_effects(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    script = textwrap.dedent(
        """
        import importlib, pkgutil, socket
        def blocked(*a, **k):
            raise SystemExit("network access at import")
        socket.socket.connect = blocked
        socket.getaddrinfo = blocked
        import tokli
        for mod in pkgutil.walk_packages(tokli.__path__, "tokli."):
            importlib.import_module(mod.name)
        print("ok")
        """
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("TOKLI_")}
    env.update(home_env(home))
    done = subprocess.run(
        [sys.executable, "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok"
    assert listing(home) == set() and listing(cwd) == set()
