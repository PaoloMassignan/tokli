"""Shared fixtures. Every test runs with a temporary HOME and without inherited TOKLI_* variables
(MD-04, MD-05), so results never depend on the developer's machine."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.helpers import home_env
from tokli.cli.main import main


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A clean environment mapping for direct calls to ``load_config``."""
    return home_env(tmp_path / "home")


@dataclass
class CliRun:
    code: int
    out: str
    err: str


@dataclass
class Cli:
    home: Path
    workdir: Path
    capsys: pytest.CaptureFixture[str]

    def run(self, *argv: str) -> CliRun:
        code = main(list(argv))
        captured = self.capsys.readouterr()
        return CliRun(code, captured.out, captured.err)


@pytest.fixture
def cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Iterator[Cli]:
    """Runs ``tokli`` in-process with a scrubbed environment and a temporary working directory."""
    for name in list(os.environ):
        if name.startswith("TOKLI_"):
            monkeypatch.delenv(name)
    home = tmp_path / "home"
    for name, value in home_env(home).items():
        monkeypatch.setenv(name, value)
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    yield Cli(home=home, workdir=workdir, capsys=capsys)
